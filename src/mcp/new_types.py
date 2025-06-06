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
RequestId = Annotated[
    int | str, "Unique identifier for a request. Can be a string or integer."
]
ProgressToken = Annotated[
    str | int, "Token used to track progress of long-running operations."
]
Cursor = Annotated[str, "Opaque string used for pagination in list operations."]
Role = Annotated[
    Literal["user", "assistant"],
    "Sender or recipient of messages and data in a conversation.",
]


RequestT = TypeVar("RequestT", bound="Request")
NotificationT = TypeVar("NotificationT", bound="Notification")
ResultT = TypeVar("ResultT", bound="Result")


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Request(ProtocolModel):
    """
    Base class for MCP requests.

    All requests must specify a method. Use `progress_token` to receive
    progress updates for long-running operations.

    Note: `progress_token` overrides `metadata["progressToken"]` if both are set.
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
    def from_protocol(cls: type[RequestT], data: dict[str, Any]) -> RequestT:
        """Convert from protocol-level representation."""

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

        # Attribute is defined on all subclasses but not on the base class. Ignore
        # linter error.
        result: dict[str, Any] = {"method": self.method}  # type: ignore[attr-defined]
        if params:
            result["params"] = params

        return result


class PaginatedRequest(Request):
    """
    Base class for MCP requests that support pagination.

    Includes an opaque cursor representing the current pagination position.
    If provided, the server should return results starting after this cursor.
    """

    cursor: Cursor | None = None
    """
    Opaque pagination token for retrieving the next page of results.
    """


class Notification(ProtocolModel):
    """
    Base class for MCP notifications.

    Notifications are one-way messages that don't expect a response.
    """

    metadata: dict[str, Any] | None = Field(default=None)
    """
    Additional notification metadata.
    """

    @classmethod
    def from_protocol(cls: type[NotificationT], data: dict[str, Any]) -> NotificationT:
        """Convert from protocol-level representation"""

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
        # Attribute is defined on all subclasses but not on the base class. Ignore
        # linter error.
        result: dict[str, Any] = {"method": self.method}  # type: ignore[attr-defined]

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
    def from_protocol(cls: type[ResultT], data: dict[str, Any]) -> ResultT:
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


class EmptyResult(Result):
    """
    Result that indicates success but carries no data.
    """

    pass


class PaginatedResult(Result):
    """
    Base class for MCP results that support pagination.

    Includes an opaque token representing the pagination position after the last
    returned result. If present, there may be more results available.
    """

    next_cursor: Cursor | None = Field(default=None, alias="nextCursor")
    """
    Token for retrieving the next page, if more results exist.
    """


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

    method: Literal["initialize"] = "initialize"
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

    method: Literal["notifications/initialized"] = "notifications/initialized"


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


# --------- Cross-cutting types ----------


class ResourceContents(ProtocolModel):
    """
    Base class for resource contents.
    """

    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]
    mime_type: str | None = Field(default=None, alias="mimeType")


class TextResourceContents(ResourceContents):
    """
    Resource contents represented as text (not binary text).
    """

    text: str
    """
    The text of the resource. Only set if the resource can be represented as text
    (not binary text).
    """


class BlobResourceContents(ResourceContents):
    """
    Resource contents represented as a binary blob.
    """

    blob: str
    """
    Base64-encoded string representing the binary data of the resource.
    """


class Annotations(ProtocolModel):
    """
    Display hints for client rendering.

    Guides how clients should use or present objects.
    """

    audience: list[Role] | Role | None = None
    """
    Target audience roles. Single role or list of roles.
    """

    priority: float | int | None = None
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
    def validate_priority(cls, v: float | int | None):
        if v is not None and not (0 <= v <= 1):
            raise ValueError("priority must be between 0 and 1")
        return v

    def to_protocol(self) -> dict[str, Any]:
        """Model dump to dict. Note 'audience' gets serialized to a list!"""
        return self.model_dump(exclude_none=True, mode="json")


class TextContent(ProtocolModel):
    """Text provided to or from an LLM."""

    type: str = Field("text", frozen=True)
    text: str
    """
    The text content of the message.
    """

    annotations: Annotations | None = None
    """
    Display hints for client use and rendering.
    """


class ImageContent(ProtocolModel):
    """
    An image provided to or from an LLM.

    Image is provided as base64-encoded data.
    """

    type: str = Field("image", frozen=True)
    mime_type: str = Field(alias="mimeType")
    data: str
    """
    The base64-encoded image data.
    """

    annotations: Annotations | None = None
    """
    Display hints for client use and rendering.
    """


class AudioContent(ProtocolModel):
    """
    Audio provided to or from an LLM.

    Audio is provided as base64-encoded data.
    """

    type: str = Field("audio", frozen=True)
    mime_type: str = Field(alias="mimeType")
    data: str
    """
    The base64-encoded audio data
    """

    annotations: Annotations | None = None
    """
    Display hints for client use and rendering.
    """


class EmbeddedResource(ProtocolModel):
    """
    The contents of a resource that is embedded in a prompt or tool call result.

    Client determines how to display the resource for the benefit of the LLM and/or
    user.
    """

    type: str = Field("resource", frozen=True)
    resource: TextResourceContents | BlobResourceContents
    annotations: Annotations | None = None
    """
    Display hints for client use and rendering.
    """


class PingRequest(Request):
    """
    Heartbeat to check connection health. Sent by client or server.

    Must be answered promptly to maintain connection.
    """

    method: Literal["ping"] = "ping"


class CancelledNotification(Notification):
    """
    Notifies that a request was cancelled.

    Sent when a request is terminated before execution or completion.
    """

    method: Literal["notifications/cancelled"] = "notifications/cancelled"
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

    method: Literal["notifications/progress"] = "notifications/progress"
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


class InputSchema(ProtocolModel):
    """
    JSON schema for the tool's input parameters.
    """

    type: Literal["object"] = Field(default="object", frozen=True)
    properties: dict[str, Any] | None = None
    required: list[str] | None = None


class ToolAnnotations(ProtocolModel):
    """
    Additional properties describing a tool to the client.

    All properties are *hints* and not guaranteed to be accurate. Clients should not
    rely on these hints to determine the tool's behavior from untrusted servers.
    """

    title: str | None = None
    """
    Human-readable title of the tool.
    """

    read_only_hint: bool = Field(default=False, alias="readOnlyHint")
    destructive_hint: bool = Field(default=True, alias="destructiveHint")
    idempotent_hint: bool = Field(default=False, alias="idempotentHint")
    open_world_hint: bool = Field(default=True, alias="openWorldHint")


class Tool(ProtocolModel):
    """
    A tool that the server can execute.
    """

    name: str
    description: str | None = None
    """
    Human-readable description of the tool. Clients can use this to improve LLM
    understanding of the tool.
    """
    input_schema: InputSchema = Field(alias="inputSchema")
    """
    JSON schema for the tool's input parameters.
    """
    annotations: ToolAnnotations | None = Field(default=None)


class ListToolsRequest(PaginatedRequest):
    """
    Request to list available tools with optional pagination.
    """

    method: Literal["tools/list"] = "tools/list"


class ListToolsResult(PaginatedResult):
    """
    Response containing available tools and pagination info.
    """

    tools: list[Tool]


class CallToolRequest(Request):
    """
    Request to call a tool.
    """

    method: Literal["tools/call"] = "tools/call"
    name: str
    arguments: dict[str, Any] | None = None


class CallToolResult(Result):
    content: list[TextContent | ImageContent | AudioContent | EmbeddedResource]
    is_error: bool = Field(default=False, alias="isError")
    """
    Whether the tool call resulted in an error.
    """


class ToolListChangedNotification(Notification):
    """
    Notification that the list of tools has changed.

    Servers can send this without clients registering for notifications.
    """

    method: Literal["notifications/tools/list_changed"] = (
        "notifications/tools/list_changed"
    )


# --------- Resource Specific ---------


class Resource(ProtocolModel):
    """
    A known resource the server can read from.
    """

    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]
    """
    Resource identifier (file path, URL, etc.).
    """

    name: str
    """
    Human-readable resource name. Client can display this to the user.
    """

    description: str | None = None
    """
    Optional resource description. Clients can use this to improve LLM understanding
    of the resource.
    """

    mime_type: str | None = Field(default=None, alias="mimeType")
    """
    MIME type of the resource content.
    """

    annotations: Annotations | None = None
    """
    Display hints for client use and rendering.
    """

    size_in_bytes: int | None = Field(default=None, alias="size")
    """
    Resource size in bytes. Used by Hosts to display file size and estimate token
    usage.
    """


class ResourceTemplate(ProtocolModel):
    """
    A template for a set of resources that the server can read from.
    """

    uri_template: str = Field(alias="uriTemplate")
    """
    URI template following RFC 6570 specification (e.g., "file:///logs/{date}.log").
    Template variables are enclosed in braces and will be expanded when requesting
    the actual resource.
    """

    name: str
    """
    Human-readable name for the type of resource this template refers to. Clients can
    use this to populate UI elements.
    """

    description: str | None = None
    """
    Human-readable description of what this template is for. Clients can use this to
    improve LLM understanding of the available resources.
    """

    mime_type: str | None = Field(default=None, alias="mimeType")
    """
    MIME type of the resource content. Only include if all resources matching this
    template have the same type.
    """

    annotations: Annotations | None = None
    """
    Display hints for client use and rendering.
    """

    def to_protocol(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, by_alias=True, mode="json")


class ListResourcesRequest(PaginatedRequest):
    """
    Request to list available resources with optional pagination.
    """

    method: Literal["resources/list"] = "resources/list"


class ListResourcesResult(PaginatedResult):
    """
    Response containing available resources and pagination info.
    """

    resources: list[Resource]
    """
    List of available resources.
    """


class ListResourceTemplatesRequest(PaginatedRequest):
    """
    Request to list available resource templates with optional pagination.
    """

    method: Literal["resources/templates/list"] = "resources/templates/list"


class ListResourceTemplatesResult(PaginatedResult):
    """
    Response containing available resource templates and pagination info.
    """

    resource_templates: list[ResourceTemplate] = Field(alias="resourceTemplates")
    """
    List of available resource templates.
    """


class ReadResourceRequest(Request):
    """
    Request to read a resource at a given URI.
    """

    method: Literal["resources/read"] = "resources/read"
    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]
    """
    URI of the resource to read.
    """


class ReadResourceResult(Result):
    """
    Response containing the content of a resource.
    """

    contents: list[TextResourceContents | BlobResourceContents]
    """
    The content of the resource.
    """


class ResourceListChangedNotification(Notification):
    method: Literal["notifications/resources/list_changed"] = (
        "notifications/resources/list_changed"
    )


class SubscribeRequest(Request):
    """
    Request to subscribe to resource update notifications for a given resource.
    """

    method: Literal["resources/subscribe"] = "resources/subscribe"
    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]


class UnsubscribeRequest(Request):
    """
    Request to unsubscribe from resource update notifications for a given resource.
    """

    method: Literal["resources/unsubscribe"] = "resources/unsubscribe"
    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]


class ResourceUpdatedNotification(Notification):
    """
    Notification that a resource has been updated.
    """

    method: Literal["notifications/resources/updated"] = (
        "notifications/resources/updated"
    )
    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]


# --------- Prompt Specific ----------


class PromptArgument(ProtocolModel):
    """
    Describes an argument that a prompt can accept.
    """

    name: str
    description: str | None = None
    """
    Human-readable description of the argument.
    """

    required: bool = Field(default=False)
    """
    Whether the argument must be provided. Defaults to False.
    """


class Prompt(ProtocolModel):
    """
    A prompt or prompt template the server offers.

    Note the prompt content is in PromptMessage objects.
    """

    name: str
    description: str | None = None
    arguments: list[PromptArgument] | None = None
    """
    List of arguments used for templating the prompt.
    """


class PromptMessage(ProtocolModel):
    """
    Describes a message as a part of a prompt.
    """

    role: Role
    content: TextContent | ImageContent | AudioContent | EmbeddedResource


class ListPromptsRequest(PaginatedRequest):
    """
    Sent by client to list available prompts and prompt templates on the server.
    """

    method: Literal["prompts/list"] = "prompts/list"


class ListPromptsResult(PaginatedResult):
    """
    Response containing available prompts and pagination info.
    """

    prompts: list[Prompt]
    """
    List of available prompts.
    """


class GetPromptRequest(Request):
    """
    Sent by client to get a specific prompt or prompt template from the server.

    If the prompt is a template, the server will return a prompt with the arguments
    filled in.
    """

    method: Literal["prompts/get"] = "prompts/get"
    name: str
    """
    The name of the prompt or prompt template.
    """

    arguments: dict[str, str] | None = None
    """
    Arguments to use for templating the prompt.
    """


class GetPromptResult(Result):
    """
    Response containing the prompt or prompt template.
    """

    description: str | None = None
    """
    Human-readable description of the prompt or prompt template.
    """

    messages: list[PromptMessage]
    """
    The prompt or prompt template messages.
    """


class PromptListChangedNotification(Notification):
    method: Literal["notifications/prompts/list_changed"] = (
        "notifications/prompts/list_changed"
    )


# --------- Logging specific ---------
LoggingLevel = Annotated[
    Literal[
        "debug",
        "info",
        "notice",
        "warning",
        "error",
        "critical",
        "alert",
        "emergency",
    ],
    "Level of logging the client wants to receive from the server.",
]


class SetLevelRequest(Request):
    """
    Request client sends to server to set/update the logging level.

    The server should send all logs at `level` and more severe.
    """

    method: Literal["logging/setLevel"] = "logging/setLevel"
    level: LoggingLevel
    """
    Client requests logs at this level and more severe.
    """


class LoggingMessageNotification(Notification):
    """
    Logging noticiation sent from server to client.

    If the client didn't set a logging level, the server can decide which messages to
    send automatically.
    """

    method: Literal["notifications/message"] = "notifications/message"
    level: LoggingLevel
    """
    Severity of the log message.
    """

    logger: str | None = None
    """
    Name of the logger issuing the message.
    """

    data: Any
    """
    Any JSON serializable data to log.
    """


# --------- Sampling specific ---------
class SamplingMessage(ProtocolModel):
    """Describes a message issued to or received from an LLM API."""

    role: Role
    content: TextContent | ImageContent | AudioContent


ModelHint = Annotated[str, "Hint for the model to use."]


class ModelPreferences(ProtocolModel):
    """
    Preferences for the model to use.
    """

    hints: list[ModelHint] | None = Field(default=None)
    cost_priority: float | None = Field(default=None, alias="costPriority")
    speed_priority: float | None = Field(default=None, alias="speedPriority")
    intelligence_priority: float | None = Field(
        default=None, alias="intelligencePriority"
    )

    @field_validator("cost_priority", "speed_priority", "intelligence_priority")
    @classmethod
    def validate_priority(cls, v: float | None) -> float | None:
        if v is not None and (v < 0 or v > 1):
            raise ValueError(f"Priority must be between 0 and 1, got {v}")
        return v


class CreateMessageRequest(Request):
    """
    Request to create a message.
    """

    method: Literal["sampling/createMessage"] = "sampling/createMessage"
    messages: list[SamplingMessage]
    model_preferences: ModelPreferences | None = Field(
        default=None, alias="modelPreferences"
    )
    system_prompt: str | None = Field(default=None, alias="systemPrompt")
    include_context: Literal["none", "thisServer", "allServers"] | None = Field(
        default=None, alias="includeContext"
    )
    temperature: float | int | None = None
    max_tokens: int = Field(alias="maxTokens")
    stop_sequences: list[str] | None = Field(default=None, alias="stopSequences")
    llm_metadata: dict[str, Any] | None = None
    """
    Metadata to pass to the LLM provider. The format is provider-specific. This is not
    MCP metadata (set that with `metadata`).
    """

    @classmethod
    def from_protocol(cls, data: dict[str, Any]) -> "CreateMessageRequest":
        """Convert from protocol-level representation."""
        # Extract protocol structure
        params = data.get("params", {})
        meta = params.get("_meta", {})

        # Build kwargs for the constructor
        kwargs = {
            "method": data["method"],
            "progress_token": meta.get("progressToken"),
        }

        # Handle MCP metadata (excluding progressToken which we handle specially)
        if meta:
            general_meta = {k: v for k, v in meta.items() if k != "progressToken"}
            if general_meta:
                kwargs["metadata"] = general_meta

        # Handle LLM metadata specially
        if "metadata" in params:
            llm_meta = params["metadata"]
            if llm_meta:  # Only set if non-empty
                kwargs["llm_metadata"] = llm_meta

        # Add other fields, respecting aliases
        for field_name, field_info in cls.model_fields.items():
            if field_name in {"method", "progress_token", "metadata", "llm_metadata"}:
                continue

            param_key = field_info.alias if field_info.alias else field_name
            if param_key in params:
                kwargs[field_name] = params[param_key]

        return cls(**kwargs)

    def to_protocol(self) -> dict[str, Any]:
        """Convert to protocol-level representation"""
        # Get the base params (excluding our special metadata handling)
        params = self.model_dump(
            exclude={"method", "progress_token", "metadata", "llm_metadata"},
            by_alias=True,
            exclude_none=True,
            mode="json",
        )

        # Handle LLM metadata directly in params
        if self.llm_metadata:
            params["metadata"] = self.llm_metadata

        # Handle MCP protocol metadata in _meta
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


class CreateMessageResult(Result):
    """The client's response to a sampling/create_message request from the server."""

    # From SamplingMessage
    role: Role
    content: TextContent | ImageContent | AudioContent

    # Own fields
    model: str
    """The name of the model that generated the message."""
    stop_reason: Literal["endTurn", "stopSequence", "maxTokens"] | str | None = Field(
        default=None, alias="stopReason"
    )
    """The reason why sampling stopped, if known."""


# --------- Completions specific ---------
class PromptReference(ProtocolModel):
    """
    Reference to a prompt.
    """

    type: Literal["ref/prompt"] = "ref/prompt"
    name: str


class ResourceReference(ProtocolModel):
    """
    Reference to a resource.
    """

    type: Literal["ref/resource"] = "ref/resource"
    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]
    """
    URI or URI template of the resource.
    """


class Completion(ProtocolModel):
    """
    Completion response containing multiple available options.
    """

    values: Annotated[list[str], Field(max_length=100)]
    total: int | None = None
    has_more: bool | None = Field(default=None, alias="hasMore")


class CompletionArgument(ProtocolModel):
    """
    Arguments for the completion request.
    """

    name: str
    value: str


class CompleteRequest(Request):
    """
    Request from client to server to ask for completion options.
    """

    method: Literal["completion/complete"] = "completion/complete"
    ref: PromptReference | ResourceReference
    argument: CompletionArgument


class CompleteResult(Result):
    completion: Completion


# --------- Roots specific ---------
class Root(ProtocolModel):
    """
    A root of the server.
    """

    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]
    """
    URI must start with file:// in this version of the protocol.
    """
    name: str | None = None

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: AnyUrl) -> AnyUrl:
        if not str(v).startswith("file://"):
            raise ValueError(
                "Root URI must start with file:// "
                "(current protocol version requirement)"
            )
        return v


class ListRootsRequest(Request):
    """
    Request to list the roots of the server.
    """

    method: Literal["roots/list"] = "roots/list"


class ListRootsResult(Result):
    """
    Response containing the roots of the server.
    """

    roots: list[Root]


class RootsListChangedNotification(Notification):
    """
    Notification that the roots of the server have changed.
    """

    method: Literal["notifications/roots/list_changed"] = (
        "notifications/roots/list_changed"
    )


# --------- JSON-RPC Types ----------


class JSONRPCRequest(ProtocolModel):
    """
    JSON-RPC 2.0 request wrapper for MCP requests.

    Wire format for requests that expect responses.
    """

    jsonrpc: str = Field(default=JSONRPC_VERSION, frozen=True)
    id: RequestId
    """
    Unique identifier for matching requests to responses. String or integer.
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


ClientRequest = (
    PingRequest
    | InitializeRequest
    | CompleteRequest
    | SetLevelRequest
    | GetPromptRequest
    | ListPromptsRequest
    | ListResourcesRequest
    | ListResourceTemplatesRequest
    | ReadResourceRequest
    | SubscribeRequest
    | UnsubscribeRequest
    | CallToolRequest
    | ListToolsRequest
)

ClientNotification = (
    CancelledNotification
    | ProgressNotification
    | InitializedNotification
    | RootsListChangedNotification
)

ClientResult = EmptyResult | CreateMessageResult | ListRootsResult

ServerRequest = PingRequest | CreateMessageRequest | ListToolsRequest

ServerNotification = (
    CancelledNotification
    | ProgressNotification
    | LoggingMessageNotification
    | ResourceUpdatedNotification
    | ResourceListChangedNotification
    | ToolListChangedNotification
    | PromptListChangedNotification
)

ServerResult = (
    EmptyResult
    | InitializeResult
    | CompleteResult
    | GetPromptResult
    | ListPromptsResult
    | ListResourceTemplatesResult
    | ListResourcesResult
    | ReadResourceResult
    | CallToolResult
    | ListToolsResult
)

JSONRPCBatchRequest = list[JSONRPCRequest | JSONRPCNotification]

JSONRPCBatchResponse = list[JSONRPCResponse | JSONRPCError]

JSONRPCMessage = (
    JSONRPCRequest
    | JSONRPCNotification
    | JSONRPCBatchRequest
    | JSONRPCResponse
    | JSONRPCError
    | JSONRPCBatchResponse
)
