from typing import Any, Literal

from pydantic import Field

from .base import PROTOCOL_VERSION, Notification, ProtocolModel, Request, Result


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
