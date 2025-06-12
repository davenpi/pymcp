"""
MCP Tools: Turn your LLM into an agent that can actually do things.

Instead of just generating text, your LLM can now:
- Search the web and read documents
- Query databases and APIs  
- Write files and run calculations
- Send emails and create calendar events

The flow is straightforward:

1. **Discovery**: LLM asks "What can I do?" via `ListToolsRequest`
2. **Decision**: LLM reads tool descriptions and decides which to use
3. **Execution**: LLM calls the tool with `CallToolRequest` 
4. **Learning**: Tool returns results (or errors) that LLM can see and learn from

Note: LLMs consume both results and errors as natural language, so they can learn from
failures and adjust their approach. This isn't just function calling—it's
giving LLMs the ability to understand what went wrong and try again.

Since LLMs consume your tool descriptions, schemas, and error messages directly, the
quality of your natural language documentation determines how effectively the LLM can
use your tools.
"""

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
