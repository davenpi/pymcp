from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
        """Convert from protocol-level representation"""
        if "method" not in data:
            raise ValueError("Invalid request data: missing 'method' field")

        method = data["method"]
        params = dict(data.get("params", {}))

        meta = params.pop("_meta", {})
        progress_token = meta.get("progressToken")

        # TODO: Think through nested fields
        return cls(
            method=method,
            progress_token=progress_token,
            **params,
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
    meta: dict[str, Any] | None = None

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "Notification":
        """Convert from protocol-level representation"""
        if "method" not in data:
            raise ValueError("Invalid notification data: missing 'method' field")

        method = data["method"]
        params = dict(data.get("params", {}))
        meta = params.pop("_meta", None) if params else None

        return cls(
            method=method,
            meta=meta,
            **params,
        )

    def to_protocol(self) -> dict[str, Any]:
        """Convert to protocol-level representation"""
        params = self.model_dump(
            exclude={"method", "meta"},
            by_alias=True,
            exclude_none=True,
        )
        if self.meta is not None:
            params["_meta"] = self.meta

        result: dict[str, Any] = {"method": self.method}
        if params:
            result["params"] = params
        return result


class Result(ProtocolModel):
    meta: dict[str, Any] | None = Field(default=None, alias="_meta")

    def to_protocol(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "Result":
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


class InitializedNotification(Notification):
    method: str = Field(default="notifications/initialized", frozen=True)


class InitializeResult(Result):
    protocol_version: str = Field(alias="protocolVersion")
    capabilities: ServerCapabilities
    server_info: Implementation = Field(alias="serverInfo")
    instructions: str | None = None


# Tool Types


class ListToolsRequest(Request):
    method: str = Field(default="tools/list", frozen=True)
    cursor: Cursor | None = None


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
        return self.model_dump(exclude_none=True)
