import asyncio
from collections.abc import Callable
from typing import Any

from mcp.protocol import CallToolRequest, CallToolResult, JSONRPCRequest, Request
from mcp.protocol.base import Error
from mcp.protocol.jsonrpc import JSONRPCError, JSONRPCResponse
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
        self._request_handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}

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

    async def send_request(
        self, request: Request, transport_metadata: dict[str, Any] | None = None
    ) -> tuple[Any, dict[str, Any] | None]:
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
            await self.transport.send(jsonrpc_request.to_wire(), transport_metadata)
            return await future
        finally:
            self._pending_requests.pop(request_id, None)

    def register_handler(
        self, method: str, handler: Callable[[dict[str, Any]], Any]
    ) -> None:
        """Register a handler for a server->client requests."""
        self._request_handlers[method] = handler

    async def _message_loop(self) -> None:
        """Background task: process incoming messages."""
        try:
            while self._running:
                print("Message loop: waiting for message...")
                message = await self.transport.receive()
                print(f"Message loop: received {message.payload}")
                await self._handle_message(message)
                print("Message loop: handled message")
        except Exception as e:
            print(f"Message loop exception: {e}")
            self._running = False
            # Cancel pending requests
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(ConnectionError("Transport closed"))

    async def _handle_message(self, message: TransportMessage) -> None:
        """Handle incoming message from transport."""
        payload = message.payload
        message_id = payload.get("id")
        print(f"Handling message: id={message_id}, payload={payload}")

        if message_id is not None and message_id in self._pending_requests:
            print(f"Found pending request for id {message_id}")
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
        elif "method" in payload and message_id is not None:
            print(f"Server request: {payload.get('method')}")
            await self._handle_server_request(message)
        elif "method" in payload and message_id is None:
            print(f"Server notification: {payload.get('method')}")
            await self._handle_notification(message)
        else:
            print(f"Unknown message type, ignoring: {payload}")
            pass

    async def _handle_notification(self, message: TransportMessage) -> None:
        """Handle notifications from server (no response needed)."""
        payload = message.payload
        method = payload["method"]

        if method in self._request_handlers:
            try:
                await self._request_handlers[method](payload.get("params", {}))
            except Exception:
                # Log the error but don't send a response (it's a notification)
                pass
        # Silently ignore unknown notifications

    async def _handle_server_request(self, message: TransportMessage) -> None:
        """Handle incoming requests from server."""
        payload = message.payload
        method = payload["method"]
        request_id = payload["id"]

        if method in self._request_handlers:
            try:
                # Call the handler
                result = await self._request_handlers[method](payload.get("params", {}))

                # Send success response
                response = JSONRPCResponse.from_result(result, request_id)
                await self.transport.send(response.to_wire(), message.metadata)
            except Exception as e:
                # Send error response
                error = Error(code=-32603, message=str(e))
                error_response = JSONRPCError.from_error(error, request_id)
                await self.transport.send(error_response.to_wire(), message.metadata)
        else:
            # Method not found
            error = Error(code=-32601, message=f"Method not found: {method}")
            error_response = JSONRPCError.from_error(error, request_id)
            await self.transport.send(error_response.to_wire(), message.metadata)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        transport_metadata: dict[str, Any] | None = None,
        return_transport_metadata: bool = False,
    ) -> CallToolResult | tuple[CallToolResult, dict[str, Any] | None]:
        """Call a tool and return the result.

        Args:
            name: Name of the tool to call
            arguments: Arguments to pass to the tool
            transport_metadata: Metadata to send with the request (auth tokens, etc.)
            return_transport_metadata: If True, return (result, transport_metadata)
                tuple.

        Returns:
            CallToolResult if return_metadata=False, otherwise tuple of
            (result, metadata)

        Raises:
            MCPError: If the tool call fails. Check .transport_metadata for HTTP
            status, etc.
        """
        request = CallToolRequest(name=name, arguments=arguments)
        raw_result, transport_meta = await self.send_request(
            request, transport_metadata
        )
        result = CallToolResult.from_protocol(raw_result)

        return (result, transport_meta) if return_transport_metadata else result
