from typing import Any, Literal

from pydantic import Field

from mcp.protocol.base import (
    Notification,
    PaginatedRequest,
    PaginatedResult,
    ProtocolModel,
    Request,
    Result,
)
from mcp.protocol.content import (
    AudioContent,
    EmbeddedResource,
    ImageContent,
    TextContent,
)


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
