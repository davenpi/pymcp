import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.protocol import CallToolRequest, CallToolResult, JSONRPCRequest, Request
from mcp.protocol.base import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    PROTOCOL_VERSION,
    Error,
    Notification,
    Result,
)
from mcp.protocol.common import CancelledNotification, EmptyResult, PingRequest
from mcp.protocol.initialization import (
    ClientCapabilities,
    Implementation,
    InitializedNotification,
    InitializeRequest,
    InitializeResult,
)
from mcp.protocol.jsonrpc import JSONRPCError, JSONRPCNotification, JSONRPCResponse
from mcp.protocol.roots import ListRootsRequest, ListRootsResult, Root
from mcp.protocol.sampling import CreateMessageRequest, CreateMessageResult
from mcp.shared.new_exceptions import MCPError
from mcp.transport.base import Transport, TransportMessage


class ClientSession:
    """
    MCP client session handling request/response over a transport.
    """

    def __init__(
        self,
        transport: Transport,
        client_info: Implementation,
        capabilities: ClientCapabilities,
        create_message_handler: Callable[
            [CreateMessageRequest], Awaitable[CreateMessageResult]
        ]
        | None = None,
        roots: list[Root] | None = None,
    ):
        self.transport = transport
        self.client_info = client_info
        self.capabilities = capabilities

        if capabilities.sampling and create_message_handler is None:
            raise ValueError(
                "create_message_handler required when sampling capability is enabled."
                " Either provide a handler or disable sampling in ClientCapabilities."
            )
        self.create_message_handler = create_message_handler

        self.roots = roots or []  # TODO: Hook this up to notifcations.

        self._request_id = 0
        self._pending_requests: dict[int, asyncio.Future[Any]] = {}
        self._buffered_responses: dict[int, tuple[Any, dict[str, Any] | None]] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._initializing: asyncio.Future[InitializeResult] | None = None
        self._initialize_result: InitializeResult | None = None
        self._initialized = False

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

    async def initialize(
        self, transport_metadata: dict[str, Any] | None = None
    ) -> InitializeResult:
        if self._initialized and self._initialize_result is not None:
            return self._initialize_result

        if self._initializing:
            return await self._initializing

        self._initializing = asyncio.create_task(
            self._do_initialize(transport_metadata)
        )
        try:
            result = await self._initializing
            return result
        finally:
            self._initializing = None

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        if self._initializing:
            await self._initializing
            return

        await self.initialize()

    def _validate_server(self, init_result: InitializeResult) -> None:
        if init_result.protocol_version != PROTOCOL_VERSION:
            raise ValueError(
                f"Protocol version mismatch: client version {PROTOCOL_VERSION} !="
                f" server version {init_result.protocol_version}"
            )

    async def _do_initialize(
        self, transport_metadata: dict[str, Any] | None = None
    ) -> InitializeResult:
        await self.start()
        init_request = InitializeRequest(
            client_info=self.client_info,  # type: ignore[call-arg]
            capabilities=self.capabilities,
        )
        request_id = self._request_id
        self._request_id += 1
        jsonrpc_request = JSONRPCRequest.from_request(init_request, request_id)

        # Set up response waiting.
        future: asyncio.Future[Any] = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            await self.transport.send(jsonrpc_request.to_wire(), transport_metadata)
            result_data, _ = await future
            init_result = InitializeResult.from_protocol(result_data)
            self._validate_server(
                init_result
            )  # TODO. SEND INITIALIZATION ERROR IF INVALID.

            initialized_notification = InitializedNotification()
            await self.send_notification(initialized_notification, transport_metadata)

            self._initialized = True
            self._initialize_result = init_result
            return init_result
        finally:
            self._pending_requests.pop(request_id, None)

    async def send_request(
        self,
        request: Request,
        transport_metadata: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> tuple[Any, dict[str, Any] | None]:
        """Send a request and wait for a response.

        Remove the request from the pending requests dictionary when the response is
        received.

        Args:
            request: The request to send
            transport_metadata: Transport specific metadata to send with the request
                (auth tokens, etc.)
            timeout: Timeout in seconds for the request.

        Returns:
            tuple[Any, dict[str, Any] | None]: The result and transport metadata.
                (result, transport_metadata).
        """
        await self.start()
        await self._ensure_initialized()

        # Generate request ID and create JSON-RPC wrapper
        request_id = self._request_id
        self._request_id += 1
        jsonrpc_request = JSONRPCRequest.from_request(request, request_id)

        future: asyncio.Future[Any] = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            await self.transport.send(jsonrpc_request.to_wire(), transport_metadata)
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            cancelled_notification = CancelledNotification(
                request_id=request_id,  # type: ignore
                reason="Request timed out",
            )
            await self.send_notification(cancelled_notification, transport_metadata)
            raise TimeoutError(f"Request {request_id} timed out after {timeout}s")
        finally:
            self._pending_requests.pop(request_id, None)

    async def send_notification(
        self,
        notification: Notification,
        transport_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send a notification to the server."""
        await self.start()
        jsonrpc_notification = JSONRPCNotification.from_notification(notification)
        await self.transport.send(jsonrpc_notification.to_wire(), transport_metadata)

    async def _message_loop(self) -> None:
        """Background task: process incoming messages."""
        try:
            while self._running:
                message = await self.transport.receive()
                await self._handle_message(message)
        except MCPError as e:
            # TODO: Handle MCPError.
            print("MCPError", e)
            pass
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

        elif message_id is not None and ("result" in payload or "error" in payload):
            # Buffer unmatched response for a short time
            self._buffered_responses[message_id] = (payload, message.metadata)
            # Optional: Log unexpected response for debugging
            # logger.debug(f"Buffered unmatched response for request ID {message_id}")

        elif "method" in payload and message_id is not None:
            try:
                request = self._parse_request(payload)
                result_or_error = await self._route_request(request)
                if isinstance(result_or_error, Result):
                    response = JSONRPCResponse.from_result(result_or_error, message_id)
                else:
                    response = JSONRPCError.from_error(result_or_error, message_id)
                await self.transport.send(response.to_wire(), message.metadata)
            except Exception as e:
                error = Error(code=INTERNAL_ERROR, message=str(e))
                error_response = JSONRPCError.from_error(error, message_id)
                await self.transport.send(error_response.to_wire(), message.metadata)

        elif "method" in payload and message_id is None:
            pass
        else:
            pass  # TODO: Handle unknown message types.

    def _parse_request(self, payload: dict[str, Any]) -> Request:
        """Parse JSON-RPC payload into typed request objects.

        Validates method name and delegates to appropriate Request subclass. This
        ensures type safety throughout the request handling process.
        """
        method = payload["method"]
        if method == "sampling/createMessage":
            return CreateMessageRequest.from_protocol(payload.get("params", {}))
        else:
            raise Exception(f"Unknown method: {method}")

    async def _route_request(self, request: Request) -> Result | Error:
        """Route typed request to appropriate handler based on capabilities.

        If the request type isn't supported by declared capabilities or if the
        required handler is not configured, return an Error.

        Returns:
            Result if the request was handled successfully. Otherwise Error.
        """
        if isinstance(request, CreateMessageRequest):
            if not self.capabilities.sampling:
                return Error(
                    code=INVALID_REQUEST, message="Sampling capability not supported"
                )
            if self.create_message_handler is None:
                return Error(
                    code=INTERNAL_ERROR, message="No create_message_handler configured"
                )
            return await self.create_message_handler(request)

        elif isinstance(request, ListRootsRequest):
            if not self.capabilities.roots:
                return Error(
                    code=INVALID_REQUEST, message="Roots capability not supported"
                )
            return ListRootsResult(roots=self.roots)

        elif isinstance(request, PingRequest):
            return EmptyResult()

        else:
            return Error(
                code=INVALID_REQUEST,
                message=f"Unknown request type: {type(request).__name__}",
            )

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
