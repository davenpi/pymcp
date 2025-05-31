from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = "2025-03-26"
JSONRPC_VERSION = "2.0"
RequestId = int | str

ProgressToken = str | int


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Request(ProtocolModel):
    method: str
    progress_token: ProgressToken | None = None

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> "Request":
        """Convert from wire format (spec-compliant JSON-RPC)"""
        method = data["method"]
        params = data.get("params", {})

        meta = params.pop("_meta", {})
        progress_token = meta.get("progressToken")

        return cls(
            method=method,
            progress_token=progress_token,
            **params,
        )

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC)"""
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


class Notification(BaseModel):
    method: str
    params: dict[str, Any] | None = None


class Result(BaseModel):
    pass


class RootsCapability(ProtocolModel):
    list_changed: bool | None = Field(default=None, alias="listChanged")


class Implementation(ProtocolModel):
    name: str
    version: str


class ClientCapabilities(ProtocolModel):
    experimental: dict[str, Any] | None = None
    roots: RootsCapability | None = None
    sampling: dict[str, Any] | None = None


class InitializeRequest(Request):
    method: str = Field(default="initialize", frozen=True)
    protocol_version: str = Field(
        default=PROTOCOL_VERSION, alias="protocolVersion", frozen=True
    )
    client_info: Implementation = Field(alias="clientInfo")
    capabilities: ClientCapabilities = Field(default_factory=ClientCapabilities)


class JSONRPCRequest(ProtocolModel):
    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    id: RequestId
    method: str
    params: dict[str, Any] | None = None

    @classmethod
    def from_request(cls, request: Request, id: RequestId) -> "JSONRPCRequest":
        """Convert from Request to JSONRPCRequest"""
        wire_data = request.to_wire()
        return cls(
            id=id,
            method=wire_data["method"],
            params=wire_data.get("params"),
        )

    def to_request(self, request_cls: type[Request]) -> Request:
        """Convert back to a Request object"""
        wire_data = self.model_dump(exclude_none=True)
        return request_cls.from_wire(wire_data)

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC)"""
        return self.model_dump(exclude_none=True)
