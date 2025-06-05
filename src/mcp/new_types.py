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

    All requests must specify a method. Use `progress_token` to receive
    progress updates for long-running operations.

    Note: `progress_token` overrides `metadata["progressToken"]` if both are set.
    """

    method: str
    """
    The request method name.
    """

    progress_token: ProgressToken | None = None
    """
    Token (str or int) to identify this request for progress updates.
    """

    metadata: dict[str, Any] | None = Field(default=None)
    """
    Additional request metadata.
    """

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_progress_token_in_metadata(cls, metadata: dict[str, Any] | None):
        if metadata and "progressToken" in metadata:
            token = metadata["progressToken"]
            if not isinstance(token, ProgressToken):
                raise ValueError(
                    f"progressToken in metadata must be str or int, got "
                    f"{type(token).__name__}. Consider using the progress_token field "
                    "instead."
                )
        return metadata

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
            mode="json",
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
    """
    Base class for MCP notifications.

    Notifications are one-way messages that don't expect a response.
    """

    method: str
    """
    The notification method name.
    """
    metadata: dict[str, Any] | None = Field(default=None)
    """
    Additional notification metadata.
    """

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
            mode="json",
        )

        result: dict[str, Any] = {"method": self.method}

        if self.metadata:
            params["_meta"] = self.metadata

        if params:
            result["params"] = params
        return result


class Result(ProtocolModel):
    """
    Base class for MCP results.

    Results are responses to requests. Each request type has a corresponding result
    type.
    """

    metadata: dict[str, Any] | None = Field(default=None)
    """
    Additional result metadata.
    """

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
            mode="json",
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
    """
    MCP error with automatic exception formatting.

    Example:
        Error(code=500, message="Server error", data=some_exception)
    """

    code: int
    """
    Error type code.
    """

    message: str
    """
    Human readable error message.
    """

    data: str | dict[str, Any] | None = None
    """
    Additional error details. Accepts strings, dicts, or Exceptions.
    Exceptions are automatically converted to formatted tracebacks.
    """

    @field_validator("data", mode="before")
    @classmethod
    def transform_data(cls, value: Any) -> str | dict[str, Any] | None:
        if isinstance(value, Exception):
            return cls._format_exception(value)
        return value

    def to_protocol(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, mode="json")

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
    """Priority level from 0 (lowest) to 1 (highest)."""

    value: float = Field(ge=0, le=1)


# --------- Capability Types ----------


class RootsCapability(ProtocolModel):
    """
    Capability for listing and monitoring filesystem roots.
    """

    list_changed: bool | None = Field(default=None, alias="listChanged")
    """
    Whether the client sends notifications when roots change.
    """


class Implementation(ProtocolModel):
    """Name and version string of the server or client."""

    name: str
    version: str


class ClientCapabilities(ProtocolModel):
    """
    Capabilities that the client supports. Sent during initialization.
    """

    experimental: dict[str, Any] | None = None
    """
    Experimental or non-standard capabilities.
    """

    roots: RootsCapability | None = None
    """
    Filesystem roots listing and monitoring.
    """

    sampling: dict[str, Any] | None = None
    """
    LLM sampling support from the host.
    """


class PromptsCapability(ProtocolModel):
    """Capabilities for prompt management and notifications."""

    list_changed: bool | None = Field(default=None, alias="listChanged")
    """
    Whether the server sends notifications when prompts change.
    """


class ResourcesCapability(ProtocolModel):
    """Capabilities for resource access and change monitoring."""

    subscribe: bool | None = None
    """
    Whether clients can subscribe to resource change updates.
    """

    list_changed: bool | None = Field(default=None, alias="listChanged")
    """
    Whether the server sends notifications when resources change.
    """


class ToolsCapability(ProtocolModel):
    """Capabilities for tool execution and change notifications."""

    list_changed: bool | None = Field(default=None, alias="listChanged")
    """
    Whether the server sends notifications when tools change.
    """


class ServerCapabilities(ProtocolModel):
    """Capabilities that the server supports, sent during initialization."""

    experimental: dict[str, Any] | None = None
    """
    Experimental or non-standard capabilities.
    """
    logging: dict[str, Any] | None = None
    """
    Loggin capability configuration.
    """
    completions: dict[str, Any] | None = None
    """
    Completion capabilities.
    """
    prompts: PromptsCapability | None = None
    """
    Prompt management capabilities.
    """
    resources: ResourcesCapability | None = None
    """
    Resource access capabilities.
    """
    tools: ToolsCapability | None = None
    """
    Tool execution capabilities.
    """


# --------- Initialization Types ----------


class InitializeRequest(Request):
    """
    Initial handshake request to establish MCP connection.

    Sent by the client to negotiate protocol version and exchange capability
    information.
    """

    method: str = Field(default="initialize", frozen=True)
    protocol_version: str = Field(
        default=PROTOCOL_VERSION, alias="protocolVersion", frozen=True
    )
    client_info: Implementation = Field(alias="clientInfo")
    """
    Information about the client software.
    """

    capabilities: ClientCapabilities = Field(default_factory=ClientCapabilities)
    """
    Capabilities the client supports.
    """


class InitializedNotification(Notification):
    """
    Confirms successful MCP connection initialization.

    Sent by the client after processing the server's InitializeResult.
    """

    method: str = Field(default="notifications/initialized", frozen=True)


class InitializeResult(Result):
    """
    Server's response to initialization, completing the MCP handshake.

    Contains server capabilities and optional setup instructions for the client.
    """

    protocol_version: str = Field(default=PROTOCOL_VERSION, alias="protocolVersion")
    capabilities: ServerCapabilities
    """
    Capabilities the server supports.
    """

    server_info: Implementation = Field(alias="serverInfo")
    """
    Information about the server software.
    """

    instructions: str | None = None
    """
    Optional setup or usage instructions for the client.
    """


# --------- One-off types ----------


class Ping(Request):
    """
    Heartbeat to check connection health. Sent by client or server.

    Must be answered promptly to maintain connection.
    """

    method: str = Field(default="ping", frozen=True)


class CancelledNotification(Notification):
    """
    Notifies that a request was cancelled.

    Sent when a request is terminated before execution or completion.
    """

    method: str = Field(default="notifications/cancelled", frozen=True)
    request_id: RequestId = Field(alias="requestId")
    """
    ID of the cancelled request.
    """

    reason: str | None = None
    """
    Optional explanation for the cancellation.
    """


class ProgressNotification(Notification):
    """
    Reports progress on a long-running operation. Typically sent by servers.

    Links to a request via its progress_token.
    """

    method: str = Field(default="notifications/progress", frozen=True)
    progress_token: ProgressToken = Field(alias="progressToken")
    """
    Token identifying the operation being tracked.
    """

    progress: float | int
    """
    Current progress amount.
    """

    total: float | int
    """
    Total expected amount when complete.
    """

    message: str | None = None
    """
    Optional progress description or status message.
    """


# --------- Tool Specific ----------


class ListToolsRequest(Request):
    """
    Request to list available tools with optional pagination.

    Use cursor for pagination - it's an opaque token with no direct relation to server
    state.
    """

    method: str = Field(default="tools/list", frozen=True)
    cursor: Cursor | None = None
    """
    Opaque pagination token for retrieving the next page of results.
    """


# --------- Resource Specific ---------


class Annotations(ProtocolModel):
    """
    Display hints for client rendering.

    Guides how clients should use or present objects to users.
    """

    audience: list[Role] | Role | None = None
    """
    Target audience roles. Single role or list of roles.
    """

    priority: float | None = None
    """
    Priority level from 0 (lowest) to 1 (highest).
    """

    @field_validator("audience", mode="before")
    @classmethod
    def validate_audience(cls, v: str | list[str] | Role | list[Role]):
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: float | None):
        if v is not None and not (0 <= v <= 1):
            raise ValueError("priority must be between 0 and 1")
        return v

    def to_protocol(self) -> dict[str, Any]:
        """Model dump to dict. Note 'audience' gets serialized to a list!"""
        return self.model_dump(exclude_none=True, mode="json")


# class Resource(ProtocolModel):
#     """
#     A know resource the server can read from.
#     """

#     uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]
#     name: str
#     description: str | None = None
#     mime_type: str | None = Field(default=None, alias="mimeType")
#     annotations: Annotations | None = None
#     size_in_bytes: int | None = Field(
#         default=None, alias="size"
#     )  # protocol calls this size


class Resource(ProtocolModel):
    """
    A known resource that the server can read from.
    """

    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]
    """
    Resource identifier (file path, URL, etc.).
    """

    name: str
    """
    Human-readable resource name.
    """

    description: str | None = None
    """
    Optional resource description.
    """

    mime_type: str | None = Field(default=None, alias="mimeType")
    """
    MIME type of the resource content.
    """

    annotations: Annotations | None = None
    """
    Display hints for client rendering.
    """

    size_in_bytes: int | None = Field(default=None, alias="size")
    """
    Resource size in bytes.
    """

    def to_protocol(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, by_alias=True, mode="json")


class ListResourcesRequest(Request):
    """
    Request to list available resources with optional pagination.
    """

    method: str = Field("resources/list", frozen=True)
    cursor: Cursor | None = None
    """
    Pagination token for retrieving the next page of results.
    """


class ListResourcesResult(Result):
    """
    Response containing available resources and pagination info.
    """

    resources: list[Resource]
    """
    List of available resources.
    """

    next_cursor: Cursor | None = Field(default=None, alias="nextCursor")
    """
    Token for retrieving the next page, if more results exist.
    """


# --------- JSON-RPC Types ----------


class JSONRPCRequest(ProtocolModel):
    """
    JSON-RPC 2.0 request wrapper for MCP requests.

    Wire format for requests that expect responses.
    """

    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    id: RequestId
    """
    Unique identifier for matching requests to responses.
    """

    request: Request
    """
    The MCP request payload.
    """

    @classmethod
    def from_request(cls, request: Request, id: RequestId) -> "JSONRPCRequest":
        """Convert from Request to JSONRPCRequest"""
        return cls(id=id, request=request)

    def to_request(self) -> Request:
        """Convert back to a Request object"""
        return self.request

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC 2.0)"""
        protocol_data = self.request.to_protocol()
        protocol_data["jsonrpc"] = self.jsonrpc
        protocol_data["id"] = self.id
        return protocol_data


class JSONRPCNotification(ProtocolModel):
    """
    JSON-RPC 2.0 notification wrapper for MCP notifications.

    Wire format for one-way messages that don't expect responses.
    """

    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    notification: Notification
    """
    The actual MCP notification payload.
    """

    @classmethod
    def from_notification(cls, notification: Notification) -> "JSONRPCNotification":
        return cls(notification=notification)

    def to_notification(self) -> Notification:
        return self.notification

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC 2.0)"""
        protocol_data = self.notification.to_protocol()
        protocol_data["jsonrpc"] = self.jsonrpc
        return protocol_data


class JSONRPCResponse(ProtocolModel):
    """
    JSON-RPC 2.0 response wrapper for successful MCP results.

    Wire format for successful request responses.
    """

    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    id: RequestId
    """
    Identifier matching the original request.
    """

    result: Result
    """
    MCP result payload.
    """

    @classmethod
    def from_result(cls, result: Result, id: RequestId) -> "JSONRPCResponse":
        """Convert from Result to JSONRPCResponse"""
        return cls(id=id, result=result)

    def to_result(self) -> Result:
        """Extract the Result object"""
        return self.result

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC 2.0)"""
        protocol_data: dict[str, Any] = {}
        protocol_data["result"] = self.result.to_protocol()
        protocol_data["jsonrpc"] = self.jsonrpc
        protocol_data["id"] = self.id
        return protocol_data


class JSONRPCError(ProtocolModel):
    """
    JSON-RPC 2.0 error wrapper for failed MCP requests.

    Wire format for request error responses.
    """

    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    id: RequestId
    """
    Identifier matching the original request.
    """

    error: Error
    """
    MCP error payload.
    """

    @classmethod
    def from_error(cls, error: Error, id: RequestId) -> "JSONRPCError":
        """Convert from Error to JSONRPCError"""
        return cls(id=id, error=error)

    def to_error(self) -> Error:
        """Extract the Error object"""
        return self.error

    def to_wire(self) -> dict[str, Any]:
        """Convert to wire format (spec-compliant JSON-RPC 2.0)"""
        protocol_data: dict[str, Any] = {}
        protocol_data["error"] = self.error.to_protocol()
        protocol_data["jsonrpc"] = self.jsonrpc
        protocol_data["id"] = self.id
        return protocol_data
