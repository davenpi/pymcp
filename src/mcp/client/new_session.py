import asyncio
from typing import Any

from mcp.protocol import CallToolRequest, CallToolResult, JSONRPCRequest, Request
from mcp.protocol.base import Error
from mcp.shared.new_exceptions import MCPError
from mcp.transport.base import Transport, TransportMessage


class ClientSession:
    """
    MCP client session.

    Handles request/response correlation and protocol logic over a trasnport.
    """

    def __init__(self, transport: Transport):
        self.transport = transport
        self._request_id = 0
        self._pending_requests: dict[int, asyncio.Future[Any]] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start the session message loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._message_loop())

    async def stop(self) -> None:
        """Stop background processing and close transport."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.transport.close()

    async def send_request(self, request: Request) -> tuple[Any, dict[str, Any] | None]:
        """Send a request and wait for a response."""
        await self.start()  # Auto-start if needed

        # Generate request ID and create JSON-RPC wrapper
        request_id = self._request_id
        self._request_id += 1
        jsonrpc_request = JSONRPCRequest.from_request(request, request_id)

        # Set up response waiting
        future: asyncio.Future[Any] = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            # Send via transport
            await self.transport.send(jsonrpc_request.to_wire())
            return await future
        finally:
            self._pending_requests.pop(request_id, None)

    async def _message_loop(self) -> None:
        """Background task: process incoming messages."""
        try:
            while self._running:
                message = await self.transport.receive()
                await self._handle_message(message)
        except Exception:
            self._running = False
            # Cancel pending requests
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(ConnectionError("Transport closed"))

    async def _handle_message(self, message: TransportMessage) -> None:
        """Handle incoming message from transport."""
        payload = message.payload
        message_id = payload.get("id")

        if message_id is not None and message_id in self._pending_requests:
            future = self._pending_requests[message_id]

            if "error" in payload:
                protocol_error = Error.from_protocol(payload["error"])
                mcp_error = MCPError(
                    protocol_error, transport_metadata=message.metadata
                )
                future.set_exception(mcp_error)
            elif "result" in payload:
                future.set_result((payload["result"], message.metadata))
            else:
                future.set_exception(Exception("Invalid response format"))
        # TODO: Handle server requests and notifications

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        return_metadata: bool = False,
    ) -> CallToolResult | tuple[CallToolResult, dict[str, Any] | None]:
        """Call a tool and return the result.

        Args:
            name: Name of the tool to call
            arguments: Arguments to pass to the tool
            return_metadata: If True, return (result, transport_metadata) tuple

        Returns:
            CallToolResult if return_metadata=False, otherwise tuple of
            (result, metadata)

        Raises:
            MCPError: If the tool call fails. Check .transport_metadata for HTTP
            status, etc.
        """
        request = CallToolRequest(name=name, arguments=arguments)
        raw_result, transport_meta = await self.send_request(request)
        result = CallToolResult.from_protocol(raw_result)

        return (result, transport_meta) if return_metadata else result
