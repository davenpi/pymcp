import traceback
from typing import Annotated, Any, Literal, TypeVar

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    UrlConstraints,
    field_validator,
)

PROTOCOL_VERSION = "2025-03-26"
JSONRPC_VERSION = "2.0"
RequestId = int | str
ProgressToken = str | int
Cursor = str
Role = Literal["user", "assistant"]

T_Request = TypeVar("T_Request", bound="Request")
T_Notification = TypeVar("T_Notification", bound="Notification")
T_Result = TypeVar("T_Result", bound="Result")


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Request(ProtocolModel):
    """
    Base class for MCP requests.

    Note: If you set both `progress_token` and `metadata["progressToken"]`,
    the `progress_token` field takes precedence.
    """

    method: str
    progress_token: ProgressToken | None = None
    metadata: dict[str, Any] | None = Field(default=None)

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_progress_token_in_metadata(cls, v: dict[str, Any] | None):
        if v and "progressToken" in v:
            token = v["progressToken"]
            if not isinstance(token, ProgressToken):
                raise ValueError(
                    f"progressToken in metadata must be str or int, got "
                    f"{type(token).__name__}. Consider using the progress_token field"
                    "instead."
                )
        return v

    @classmethod
    def from_protocol(cls: type[T_Request], data: dict[str, Any]) -> T_Request:
        """Convert from protocol-level representation."""
        method_field = cls.model_fields.get("method")
        if method_field and isinstance(method_field.default, str):
            expected_method = method_field.default
            actual_method = data.get("method")
            if actual_method != expected_method:
                raise ValueError(
                    f"Can't create {cls.__name__} from '{actual_method}' method"
                )

        # Extract protocol structure
        params = data.get("params", {})
        meta = params.get("_meta", {})

        # Build kwargs for the constructor
        kwargs = {
            "method": data["method"],
            "progress_token": meta.get("progressToken"),
        }

        # Handle general metadata (excluding progressToken which we handle specially)
        if meta:
            general_meta = {k: v for k, v in meta.items() if k != "progressToken"}
            if general_meta:
                kwargs["metadata"] = general_meta

        # Add subclass-specific fields, respecting aliases
        for field_name, field_info in cls.model_fields.items():
            if field_name in {"method", "progress_token", "metadata"}:
                continue

            param_key = field_info.alias if field_info.alias else field_name
            if param_key in params:
                kwargs[field_name] = params[param_key]

        return cls(**kwargs)

    def to_protocol(self) -> dict[str, Any]:
        """Convert to protocol-level representation"""
        params = self.model_dump(
            exclude={"method", "progress_token", "metadata"},
            by_alias=True,
            exclude_none=True,
        )

        meta: dict[str, Any] = {}
        if self.metadata:
            meta.update(self.metadata)
        if self.progress_token is not None:
            meta["progressToken"] = self.progress_token

        if meta:
            params["_meta"] = meta

        result: dict[str, Any] = {"method": self.method}
        if params:
            result["params"] = params

        return result


class Notification(ProtocolModel):
    method: str
    metadata: dict[str, Any] | None = Field(default=None)

    @classmethod
    def from_protocol(
        cls: type[T_Notification], data: dict[str, Any]
    ) -> T_Notification:
        """Convert from protocol-level representation"""
        # Validate method if this is a concrete subclass
        method_field = cls.model_fields.get("method")
        if method_field and isinstance(method_field.default, str):
            expected_method = method_field.default
            actual_method = data.get("method")
            if actual_method != expected_method:
                raise ValueError(
                    f"Can't create {cls.__name__} from '{actual_method}' method"
                )

        # Extract params
        params = data.get("params", {})
        meta = params.get("_meta")

        # Build kwargs for the constructor
        kwargs = {
            "method": data["method"],
        }
        if meta:
            kwargs["metadata"] = meta

        # Add subclass-specific fields, respecting aliases
        for field_name, field_info in cls.model_fields.items():
            if field_name == "method":
                continue

            # Use the alias if it exists, otherwise use the field name
            param_key = field_info.alias if field_info.alias else field_name

            if param_key in params:
                kwargs[field_name] = params[param_key]

        return cls(**kwargs)

    def to_protocol(self) -> dict[str, Any]:
        """Convert to protocol-level representation"""
        params = self.model_dump(
            exclude={"method", "metadata"},
            by_alias=True,
            exclude_none=True,
        )

        result: dict[str, Any] = {"method": self.method}

        if self.metadata:
            params["_meta"] = self.metadata

        if params:
            result["params"] = params
        return result


class Result(ProtocolModel):
    metadata: dict[str, Any] | None = Field(default=None)

    @classmethod
    def from_protocol(cls: type[T_Result], data: dict[str, Any]) -> T_Result:
        """Convert from protocol-level representation."""

        # Extract metadata
        meta = data.get("_meta", {})

        # Build kwargs for the constructor
        kwargs: dict[str, Any] = {}

        # Handle metadata
        if meta:
            kwargs["metadata"] = meta

        # Add subclass-specific fields, respecting aliases
        for field_name, field_info in cls.model_fields.items():
            if field_name == "metadata":
                continue

            # Use the alias if it exists, otherwise use the field name
            param_key = field_info.alias if field_info.alias else field_name

            if param_key in data:
                kwargs[field_name] = data[param_key]

        return cls(**kwargs)

    def to_protocol(self) -> dict[str, Any]:
        """Convert to protocol-level representation"""
        result = self.model_dump(
            exclude={"metadata"},
            by_alias=True,
            exclude_none=True,
        )

        # Add metadata if present
        if self.metadata:
            result["_meta"] = self.metadata

        return result


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
        return cls.model_validate(
            {
                "code": data["code"],
                "message": data["message"],
                "data": data.get("data"),
            }
        )


# --------- Priorities ---------
class Priority(ProtocolModel):
    """Priority between 0 (not important) and 1 (very important)"""

    value: float = Field(ge=0, le=1)


# --------- Capability Types ----------


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


# --------- Initialization Types ----------


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
    protocol_version: str = Field(default=PROTOCOL_VERSION, alias="protocolVersion")
    capabilities: ServerCapabilities
    server_info: Implementation = Field(alias="serverInfo")
    instructions: str | None = None


# --------- One-off types ----------


class Ping(Request):
    method: str = Field(default="ping", frozen=True)


class CancelledNotification(Notification):
    method: str = Field(default="notifications/cancelled", frozen=True)
    request_id: RequestId = Field(alias="requestId")
    reason: str | None = None


class ProgressNotification(Notification):
    method: str = Field(default="notifications/progress", frozen=True)
    progress_token: ProgressToken = Field(alias="progressToken")
    progress: float | int
    total: float | int
    message: str | None = None


# --------- Tool Specific ----------


class ListToolsRequest(Request):
    """List tools request.

    Cursor is opaque. No direct relation to the server's state. If it's provided,
    the server should return the next page of tools.
    """

    method: str = Field(default="tools/list", frozen=True)
    cursor: Cursor | None = None


# --------- Resource Specific ---------


class Annotations(ProtocolModel):
    """Annotations for client. Client can use to decide how objects are displayed.

    Attributes:
        audience: List of roles, either "user" or "assistant".
        priority: Priority value between 0 (lowest) and 1 (highest), or None.
    """

    audience: list[Role] | None = None
    priority: float | None = None

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: float | None):
        if v is not None and not (0 <= v <= 1):
            raise ValueError("priority must be between 0 and 1")
        return v

    @field_validator("audience", mode="before")
    @classmethod
    def validate_audience(cls, v: str | list[str]):
        if isinstance(v, str):
            return [v]
        return v

    def to_protocol(self) -> dict[str, Any]:
        """Model dump to dict. Note 'audience' gets serialized to a list!"""
        return self.model_dump(exclude_none=True)


class Resource(ProtocolModel):
    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]
    name: str
    description: str | None = None
    mime_type: str | None = Field(default=None, alias="mimeType")
    annotations: Annotations | None = None
    size_in_bytes: int | None = Field(
        default=None, alias="size"
    )  # protocol calls this size

    def to_protocol(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, by_alias=True, mode="json")


class ListResourcesRequest(Request):
    method: str = Field("resources/list", frozen=True)
    cursor: Cursor | None = None


# class ListResourcesResult(Result):
#     resources: list[Resources]

#     @classmethod
#     def from_protocol(cls, data: dict[str, Any]) -> "ListResourcesResult":
#         pass cls()

# --------- JSON-RPC Types ----------


class JSONRPCRequest(ProtocolModel):
    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    id: RequestId
    request: Request

    @classmethod
    def from_request(cls, request: Request, id: RequestId) -> "JSONRPCRequest":
        """Convert from Request to JSONRPCRequest"""
        return cls(id=id, request=request)

    def to_request(self) -> Request:
        """Convert back to a Request object"""
        return self.request

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC)"""
        protocol_data = self.request.to_protocol()
        protocol_data["jsonrpc"] = self.jsonrpc
        protocol_data["id"] = self.id
        return protocol_data


class JSONRPCNotification(ProtocolModel):
    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    notification: Notification

    @classmethod
    def from_notification(cls, notification: Notification) -> "JSONRPCNotification":
        return cls(notification=notification)

    def to_notification(self) -> Notification:
        return self.notification

    def to_wire(self) -> dict[str, Any]:
        protocol_data = self.notification.to_protocol()
        protocol_data["jsonrpc"] = self.jsonrpc
        return protocol_data


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
        protocol_data: dict[str, Any] = {}
        protocol_data["result"] = self.result.to_protocol()
        protocol_data["jsonrpc"] = self.jsonrpc
        protocol_data["id"] = self.id
        return protocol_data


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
        protocol_data: dict[str, Any] = {}
        protocol_data["error"] = self.error.to_protocol()
        protocol_data["jsonrpc"] = self.jsonrpc
        protocol_data["id"] = self.id
        return protocol_data
