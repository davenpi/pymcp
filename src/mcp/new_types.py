import traceback
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROTOCOL_VERSION = "2025-03-26"
JSONRPC_VERSION = "2.0"
RequestId = int | str
ProgressToken = str | int
Cursor = str


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Request(ProtocolModel):
    method: str
    progress_token: ProgressToken | None = None

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "Request":
        """Convert from protocol-level representation.

        Ignores metadata aside from progress token.
        """
        params = data.get("params", {})
        meta = params.get("_meta", {})

        return cls(
            method=data["method"],
            progress_token=meta.get("progressToken"),
        )

    def to_protocol(self) -> dict[str, Any]:
        """Convert to protocol-level representation"""
        params = self.model_dump(
            exclude={"method", "progress_token"},
            by_alias=True,
            exclude_none=True,
        )

        if self.progress_token is not None:
            params["_meta"] = {"progressToken": self.progress_token}

        result: dict[str, Any] = {"method": self.method}
        if params:
            result["params"] = params

        return result


class Notification(ProtocolModel):
    method: str

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "Notification":
        """Convert from protocol-level representation"""
        return cls(method=data["method"])

    def to_protocol(self) -> dict[str, Any]:
        """Convert to protocol-level representation

        Method and params are siblings in the spec.
        """
        params = self.model_dump(
            exclude={"method"},
            by_alias=True,
            exclude_none=True,
        )

        result: dict[str, Any] = {"method": self.method}
        if params:
            result["params"] = params
        return result


class Result(ProtocolModel):
    def to_protocol(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "Result":
        raise NotImplementedError("Use concrete Result subclasses")


PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class Error(ProtocolModel):
    """MCP Error type.

    The 'data' field accepts str, dict, Exception, or None.
    Exceptions are automatically formatted for transmission.
    """

    code: int
    message: str
    data: str | dict[str, Any] | None = None

    @field_validator("data", mode="before")
    @classmethod
    def transform_data(cls, value: Any) -> str | dict[str, Any] | None:
        if isinstance(value, Exception):
            return cls._format_exception(value)
        return value

    def to_protocol(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @staticmethod
    def _format_exception(exc: Exception) -> str:
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "Error":
        return cls(**data)


# Capability Types


class RootsCapability(ProtocolModel):
    list_changed: bool | None = Field(default=None, alias="listChanged")


class Implementation(ProtocolModel):
    name: str
    version: str


class ClientCapabilities(ProtocolModel):
    experimental: dict[str, Any] | None = None
    roots: RootsCapability | None = None
    sampling: dict[str, Any] | None = None


class PromptsCapability(ProtocolModel):
    list_changed: bool | None = Field(default=None, alias="listChanged")


class ResourcesCapability(ProtocolModel):
    subscribe: bool | None = None
    list_changed: bool | None = Field(default=None, alias="listChanged")


class ToolsCapability(ProtocolModel):
    list_changed: bool | None = Field(default=None, alias="listChanged")


class ServerCapabilities(ProtocolModel):
    experimental: dict[str, Any] | None = None
    logging: dict[str, Any] | None = None
    completions: dict[str, Any] | None = None
    prompts: PromptsCapability | None = None
    resources: ResourcesCapability | None = None
    tools: ToolsCapability | None = None


## Initialization Types


class InitializeRequest(Request):
    method: str = Field(default="initialize", frozen=True)
    protocol_version: str = Field(
        default=PROTOCOL_VERSION, alias="protocolVersion", frozen=True
    )
    client_info: Implementation = Field(alias="clientInfo")
    capabilities: ClientCapabilities = Field(default_factory=ClientCapabilities)

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "InitializeRequest":
        """Convert from protocol-level representation"""
        params = data.get("params", {})
        meta = params.get("_meta", {})

        flattened = {
            "method": data["method"],
            "progress_token": meta.get("progressToken"),
            **{k: v for k, v in params.items() if k != "_meta"},
        }

        return cls(**flattened)


class InitializedNotification(Notification):
    method: str = Field(default="notifications/initialized", frozen=True)

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "InitializedNotification":
        params = data.get("params", {})
        _ = params.get("_meta", {})

        flattened = {
            "method": data["method"],
            **{k: v for k, v in params.items() if k != "_meta"},
        }

        return cls(**flattened)


class InitializeResult(Result):
    protocol_version: str = Field(alias="protocolVersion")
    capabilities: ServerCapabilities
    server_info: Implementation = Field(alias="serverInfo")
    instructions: str | None = None

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "InitializeResult":
        flattened = {
            **{k: v for k, v in data.items() if k != "_meta"},
        }

        return cls(**flattened)


# --------- One off types ----------


class Ping(Request):
    method: str = Field(default="ping", frozen=True)

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "Ping":
        method = data["method"]
        if method != "ping":
            raise ValueError(f"Can't create Ping from '{method}' request.")
        return cls()


class CancelledNotification(Notification):
    method: str = Field(default="notifications/cancelled", frozen=True)
    request_id: RequestId = Field(alias="requestId")
    reason: str | None = None

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "CancelledNotification":
        params = data["params"]
        flattened = {"method": data["method"], **params}
        return cls(**flattened)


# class ProgressNotification(Notification):
#     method: str = Field(default="notifications/progress", frozen=True)
#     progress_token: ProgressToken = Field(alias="progressToken")
#     progress: float | int
#     total: float | int
#     message: str | None = None

#     @classmethod
#     def from_protocol(cls, data: dict[str, Any]) -> "ProgressNotification":
#         params: dict[str, int | float| str] = data["params"]
#         method = data["method"]
#         if method != "notifications/progress":
#             raise ValueError(
#                 f"Can't create ProgressNotification from '{method}' method"
#             )
#         flattened = {"method": method, **params}
#         return cls(**flattened)


# ---------- Tool Specific ----------


class ListToolsRequest(Request):
    method: str = Field(default="tools/list", frozen=True)
    cursor: Cursor | None = None  # Cursor string is opaque. No meaning.

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "ListToolsRequest":
        """Convert from protocol-level representation"""
        params = data.get("params", {})
        meta = params.get("_meta", {})

        flattened = {
            "method": data["method"],
            "progress_token": meta.get("progressToken"),
            **{k: v for k, v in params.items() if k != "_meta"},
        }

        return cls(**flattened)


#

## JSON-RPC Types


class JSONRPCRequest(ProtocolModel):
    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    id: RequestId
    method: str
    params: dict[str, Any] | None = None

    @classmethod
    def from_request(cls, request: Request, id: RequestId) -> "JSONRPCRequest":
        """Convert from Request to JSONRPCRequest"""
        protocol_data = request.to_protocol()
        return cls(
            id=id,
            method=protocol_data["method"],
            params=protocol_data.get("params"),
        )

    def to_request(self, request_cls: type[Request]) -> Request:
        """Convert back to a Request object"""
        protocol_data = self.model_dump(exclude={"jsonrpc", "id"}, exclude_none=True)
        return request_cls.from_protocol(protocol_data)

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC)"""
        return self.model_dump(exclude_none=True, by_alias=True)


class JSONRPCResponse(ProtocolModel):
    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    id: RequestId
    result: Result

    @classmethod
    def from_result(cls, result: Result, id: RequestId) -> "JSONRPCResponse":
        """Convert from Result to JSONRPCResponse"""
        return cls(id=id, result=result)

    def to_result(self) -> Result:
        """Extract the Result object"""
        return self.result

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC)"""
        return self.model_dump(exclude_none=True, by_alias=True)


class JSONRPCError(ProtocolModel):
    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    id: RequestId
    error: Error

    @classmethod
    def from_error(cls, error: Error, id: RequestId) -> "JSONRPCError":
        """Convert from Error to JSONRPCError"""
        return cls(id=id, error=error)

    def to_error(self) -> Error:
        """Extract the Error object"""
        return self.error

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC)"""
        return self.model_dump(exclude_none=True)
