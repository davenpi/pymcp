import asyncio
from typing import Any

from mcp.protocol import JSONRPCRequest, Request
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

    async def request(self, request: Request) -> Any:
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
                future.set_exception(Exception(f"RPC Error: {payload['error']}"))
            elif "result" in payload:
                future.set_result(payload["result"])
            else:
                future.set_exception(Exception("Invalid response format"))
        # TODO: Handle server requests and notifications
