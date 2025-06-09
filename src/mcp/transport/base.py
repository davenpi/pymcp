"""Transport layer abstraction for MCP protocol."""

from abc import ABC, abstractmethod
from types import TracebackType

import mcp.protocol as protocol


class Transport(ABC):
    """Abstract transport for MCP message delivery.

    Handles the mechanics of sending and receiving JSON-RPC messages
    without knowledge of protocol semantics or message correlation.
    """

    @abstractmethod
    async def send(self, message: protocol.JSONRPCMessage) -> None:
        """Send a JSON-RPC message."""

    @abstractmethod
    async def receive(self) -> protocol.JSONRPCMessage:
        """Receive the next JSON-RPC message."""

    @abstractmethod
    async def close(self) -> None:
        """Close the transport."""

    async def __aenter__(self) -> "Transport":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()
