import asyncio
from unittest.mock import AsyncMock

import pytest

from mcp.client.new_session import ClientSession
from mcp.protocol.base import INTERNAL_ERROR, PROTOCOL_VERSION
from mcp.protocol.common import CancelledNotification, PingRequest
from mcp.protocol.content import TextContent
from mcp.protocol.initialization import (
    ClientCapabilities,
    Implementation,
    RootsCapability,
)
from mcp.protocol.logging import LoggingMessageNotification
from mcp.protocol.roots import Root
from mcp.protocol.sampling import (
    CreateMessageRequest,
    CreateMessageResult,
    SamplingMessage,
)
from mcp.shared.new_exceptions import MCPError
from tests.new_client.mock_transport import MockTransport


class TestClientSessionLifecycle:
    @pytest.fixture(autouse=True)
    def setup_fixtures(self):
        self.transport = MockTransport()
        self.session = ClientSession(
            self.transport,
            client_info=Implementation(name="test-client", version="1.0.0"),
            capabilities=ClientCapabilities(),
        )

    async def test_session_starts_not_running(self):
        assert self.session._running is False
        assert self.session._task is None

    async def test_start_sets_running_to_true(self):
        await self.session.start()
        assert self.session._running is True
        assert self.session._task is not None
        await self.session.stop()

    async def test_start_when_already_running_does_nothing(self):
        await self.session.start()
        first_task = self.session._task
        await self.session.start()
        assert self.session._task is first_task
        await self.session.stop()

    async def test_stop_sets_running_to_false(self):
        await self.session.start()
        assert self.session._running is True
        await self.session.stop()
        assert self.session._running is False

    async def test_stop_cancels_background_task(self):
        await self.session.start()
        task = self.session._task
        assert task is not None

        await self.session.stop()
        assert self.session._task is None
        assert task.cancelled()

    async def test_stop_closes_transport(self):
        await self.session.start()
        close_mock = AsyncMock()
        self.transport.close = close_mock
        await self.session.stop()
        close_mock.assert_awaited_once()

    async def test_stop_when_not_running_still_closes_transport(self):
        # Never started
        close_mock = AsyncMock()
        self.transport.close = close_mock
        await self.session.stop()
        close_mock.assert_awaited_once()

    async def test_request_timeout_does_not_affect_subsequent_requests(self):
        self.session._initialized = True

        # First request will timeout
        request1 = PingRequest()
        with pytest.raises(TimeoutError):
            await self.session.send_request(request1, timeout=1e-9)

        # Second request should work fine
        request2 = PingRequest()
        self.transport.queue_response(request_id=1, result={})

        result, _ = await self.session.send_request(request2)

        assert result == {}
        assert self.session._running is True
        assert self.session._pending_requests == {}
        assert len(self.transport.sent_messages) == 3  # 1 ping, 1 cancel, 1 response

        await self.session.stop()


class TestClientSessionRequestResponse:
    @pytest.fixture(autouse=True)
    def setup_fixtures(self):
        self.transport = MockTransport()
        self.session = ClientSession(
            self.transport,
            client_info=Implementation(name="test-client", version="1.0.0"),
            capabilities=ClientCapabilities(),
        )

    async def test_response_with_unknown_id_doesnt_hang(self):
        await self.session.start()

        # Queue a response for a request that was never sent
        self.transport.queue_response(request_id=999, result={"data": "orphaned"})

        # Queue a second message to prove the loop is still processing
        self.transport.queue_message({"test": "marker"})

        # The loop should still be running (not hung)
        assert self.session._running is True
        assert not self.session._task.done()

        await self.session.stop()

    async def test_malformed_response_doesnt_crash_message_loop(self):
        """Malformed response should not crash the message loop."""
        await self.session.start()

        # Queue a response missing both result and error
        self.transport.queue_message(
            {
                "jsonrpc": "2.0",
                "id": 123,
                # Missing "result" or "error"
            }
        )

        # Loop should still be running
        assert self.session._running is True

        await self.session.stop()

    async def test_concurrent_requests_out_of_order_responses(self):
        """Test that out-of-order responses correlate correctly."""
        self.session._initialized = True

        # Send both requests first
        request1 = PingRequest()
        request2 = PingRequest()

        # Start both requests (don't await yet)
        task1 = asyncio.create_task(self.session.send_request(request1))
        task2 = asyncio.create_task(self.session.send_request(request2))

        # Now queue responses in reverse order
        self.transport.queue_response(1, {"result": "second"})
        self.transport.queue_response(0, {"result": "first"})

        # Both should complete correctly despite reverse order
        result1, _ = await task1
        result2, _ = await task2

        assert result1 == {"result": "first"}
        assert result2 == {"result": "second"}

        await self.session.stop()

    async def test_request_timeout_send_cancellation_and_raises(self):
        self.session._initialized = True

        request = PingRequest()
        with pytest.raises(TimeoutError):
            await self.session.send_request(request, timeout=1e-9)

        assert self.session._pending_requests == {}

        cancel_message = self.transport.sent_messages[-1].payload
        assert cancel_message["method"] == "notifications/cancelled"

        await self.session.stop()

    async def test_send_notification_sends_message_to_transport(self):
        notification = CancelledNotification(request_id=42, reason="test")
        await self.session.send_notification(notification)

        sent_message = self.transport.sent_messages[-1].payload
        assert sent_message["method"] == "notifications/cancelled"
        assert sent_message["params"]["requestId"] == 42
        assert sent_message["params"]["reason"] == "test"
        assert "id" not in sent_message  # Notifications don't have IDs

        await self.session.stop()

    async def test_send_notification_propagates_transport_errors(self):
        # Make transport.send raise
        self.transport.closed = True

        notification = CancelledNotification(request_id=42, reason="test")

        with pytest.raises(ConnectionError, match="Transport closed"):
            await self.session.send_notification(notification)

        await self.session.stop()

    async def test_notification_handler_parses_and_queues_notification(self):
        self.session._initialized = True

        # Send a logging notification
        notification_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {"level": "info", "data": {"message": "test log"}},
        }
        self.transport.queue_message(notification_payload)

        await self.session.start()

        # Should be queued for consumption
        notification = await self.session.notifications.get()
        assert isinstance(notification, LoggingMessageNotification)
        assert notification.level == "info"

        await self.session.stop()

    async def test_notification_handler_does_not_crash_on_unknown_method(self):
        self.session._initialized = True

        bad_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/unknown",
            "params": {},
        }
        good_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {"level": "info", "data": {"message": "test log"}},
        }
        self.transport.queue_message(bad_notification)

        await self.session.start()

        # Should not break the session - notification queue should be empty
        assert self.session.notifications.empty()
        assert self.session._running is True

        self.transport.queue_message(good_notification)
        notification = await self.session.notifications.get()
        assert isinstance(notification, LoggingMessageNotification)
        assert notification.level == "info"

        await self.session.stop()

    # async def test_send_request_enforces_initialization(self):
    #     request = PingRequest()

    #     # Should trigger initialization automatically
    #     self.transport.queue_response(
    #         request_id=0,
    #         result={
    #             "protocolVersion": PROTOCOL_VERSION,
    #             "capabilities": {},
    #             "serverInfo": {"name": "test", "version": "1.0"},
    #         },
    #     )
    #     self.transport.queue_response(request_id=1, result={})
    #     result, _ = await self.session.send_request(request)

    #     assert result == {}
    #     assert self.session._initialized is True

    #     await self.session.stop()
    async def test_response_handler_resolves_pending_request_with_result(self):
        self.session._initialized = True

        # Set up a pending request manually
        request_id = 42
        future = asyncio.Future()
        self.session._pending_requests[request_id] = future

        # Send success response
        response_payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"data": "test"},
        }
        self.transport.queue_message(response_payload, metadata={"test": "meta"})

        await self.session.start()

        # Future should be resolved with result and metadata
        result, metadata = await future
        assert result == {"data": "test"}
        assert metadata == {"test": "meta"}

        await self.session.stop()

    async def test_response_handler_resolves_pending_request_with_error(self):
        self.session._initialized = True

        # Set up pending request
        request_id = 42
        future = asyncio.Future()
        self.session._pending_requests[request_id] = future

        # Send error response
        error_payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -1, "message": "test error"},
        }
        self.transport.queue_message(error_payload)

        await self.session.start()

        # Future should be resolved with MCPError
        with pytest.raises(MCPError) as exc_info:
            await future
        assert exc_info.value.error.message == "test error"

        await self.session.stop()

    async def test_response_handler_buffers_orphaned_response(self):
        self.session._initialized = True

        # Send response with no matching pending request
        orphaned_payload = {"jsonrpc": "2.0", "id": 999, "result": {"orphaned": True}}
        self.transport.queue_message(orphaned_payload, metadata={"meta": "data"})

        await self.session.start()

        # Wait for background message loop to process the queued message
        await asyncio.sleep(0.001)

        # Should be buffered, not cause errors
        assert 999 in self.session._buffered_responses
        buffered_payload, buffered_metadata = self.session._buffered_responses[999]
        assert buffered_payload["result"] == {"orphaned": True}
        assert buffered_metadata == {"meta": "data"}

        await self.session.stop()

    async def test_request_handler_responds_to_ping(self):
        self.session._initialized = True

        # Send a ping request
        ping_payload = {"jsonrpc": "2.0", "method": "ping", "id": 42}
        self.transport.queue_message(ping_payload)

        await self.session.start()

        # Wait for message processing
        await asyncio.sleep(0.001)

        # Should have sent back a response
        response_message = self.transport.sent_messages[-1].payload
        assert response_message["jsonrpc"] == "2.0"
        assert response_message["id"] == 42
        assert response_message["result"] == {}

        await self.session.stop()

    async def test_request_handler_rejects_list_roots_without_capability(self):
        self.session._initialized = True
        self.session.capabilities.roots = None
        # Note: session starts with no roots capability by default

        list_roots_payload = {"jsonrpc": "2.0", "method": "roots/list", "id": 42}
        self.transport.queue_message(list_roots_payload)

        await self.session.start()
        await asyncio.sleep(0.001)

        # Should send error response
        response_message = self.transport.sent_messages[-1].payload
        assert response_message["jsonrpc"] == "2.0"
        assert response_message["id"] == 42
        assert "error" in response_message
        assert (
            "does not support roots capability" in response_message["error"]["message"]
        )

        await self.session.stop()

    async def test_request_handler_returns_configured_roots(self):
        # Set up session with roots capability and some roots
        roots = [Root(uri="file:///test", name="test")]
        self.session.capabilities.roots = RootsCapability()
        self.session.roots = roots
        self.session._initialized = True

        list_roots_payload = {"jsonrpc": "2.0", "method": "roots/list", "id": 42}
        self.transport.queue_message(list_roots_payload)

        await self.session.start()
        await asyncio.sleep(0.001)

        # Should return the configured roots
        response_message = self.transport.sent_messages[-1].payload
        assert response_message["id"] == 42
        assert "result" in response_message
        assert response_message["result"]["roots"] == [
            root.model_dump(mode="json") for root in roots
        ]

        await self.session.stop()

    async def test_request_handler_rejects_create_message_without_capability(self):
        self.session._initialized = True
        self.session.capabilities.sampling = False

        sampling_message = SamplingMessage(
            role="user",
            content=TextContent(text="Hello, world!"),
        )

        create_message_payload = {
            "jsonrpc": "2.0",
            "method": "sampling/createMessage",
            "id": 42,
            "params": {
                "messages": [sampling_message.model_dump(mode="json")],
                "maxTokens": 100,
            },
        }
        self.transport.queue_message(create_message_payload)

        await self.session.start()
        await asyncio.sleep(0.001)

        # Should send error response
        response_message = self.transport.sent_messages[-1].payload
        assert response_message["jsonrpc"] == "2.0"
        assert response_message["id"] == 42
        assert "error" in response_message
        assert (
            "does not support sampling capability"
            in response_message["error"]["message"]
        )

        await self.session.stop()

    async def test_request_handler_rejects_create_message_without_handler(self):
        # Enable capability but don't provide handler
        self.session.capabilities.sampling = True
        self.session._initialized = True

        sampling_message = SamplingMessage(
            role="user",
            content=TextContent(text="Hello, world!"),
        )

        create_message_payload = {
            "jsonrpc": "2.0",
            "method": "sampling/createMessage",
            "id": 42,
            "params": {
                "messages": [sampling_message.model_dump(mode="json")],
                "maxTokens": 100,
            },
        }
        self.transport.queue_message(create_message_payload)

        await self.session.start()
        await asyncio.sleep(0.001)

        # Should send error response
        response_message = self.transport.sent_messages[-1].payload
        assert "error" in response_message
        assert (
            "Sampling capability enabled but internal handler not configured"
            in response_message["error"]["message"]
        )

        await self.session.stop()

    async def test_request_handler_calls_create_message_handler(self):
        self.session.capabilities.sampling = True

        async def mock_handler(request: CreateMessageRequest) -> CreateMessageResult:
            return CreateMessageResult(
                role="assistant",
                content=TextContent(text="test response"),
                model="test-model",
                stop_reason="endTurn",
            )

        self.session.create_message_handler = mock_handler
        self.session._initialized = True

        sampling_message = SamplingMessage(
            role="user",
            content=TextContent(text="Hello, world!"),
        )

        create_message_payload = {
            "jsonrpc": "2.0",
            "method": "sampling/createMessage",
            "id": 42,
            "params": {
                "messages": [sampling_message.model_dump(mode="json")],
                "maxTokens": 100,
            },
        }
        self.transport.queue_message(create_message_payload)

        await self.session.start()
        await asyncio.sleep(0.001)

        # Should successfully call handler and return result
        response_message = self.transport.sent_messages[-1].payload
        assert response_message["jsonrpc"] == "2.0"
        assert response_message["id"] == 42
        assert "result" in response_message
        assert response_message["result"]["model"] == "test-model"
        assert response_message["result"]["content"]["text"] == "test response"

        await self.session.stop()

    async def test_request_handler_rejects_malformed_id(self):
        self.session._initialized = True

        # Test different types of malformed IDs
        test_cases = [
            {"jsonrpc": "2.0", "method": "ping"},  # Missing ID
            {"jsonrpc": "2.0", "method": "ping", "id": None},  # Null ID
            {"jsonrpc": "2.0", "method": "ping", "id": {"not": "valid"}},  # Object ID
            {"jsonrpc": "2.0", "method": "ping", "id": [1, 2, 3]},  # Array ID
        ]

        for malformed_payload in test_cases:
            self.transport.queue_message(malformed_payload)

        await self.session.start()
        await asyncio.sleep(0.001)

        # Should have attempted to send error responses, but may have failed due to bad
        # IDs. The key thing is the session should still be running
        assert self.session._running is True

        # Test that valid requests still work after malformed ones
        valid_payload = {"jsonrpc": "2.0", "method": "ping", "id": 42}
        self.transport.queue_message(valid_payload)
        await asyncio.sleep(0.001)

        # Should have at least one successful response for the valid request
        valid_responses = [
            msg for msg in self.transport.sent_messages if msg.payload.get("id") == 42
        ]
        assert len(valid_responses) == 1

        await self.session.stop()

    async def test_create_message_handler_exception_returns_internal_error(self):
        self.session.capabilities.sampling = True
        self.session._initialized = True

        async def broken_handler(request: CreateMessageRequest) -> CreateMessageResult:
            raise ValueError("Something went wrong in user code!")

        self.session.create_message_handler = broken_handler

        sampling_message = SamplingMessage(
            role="user",
            content=TextContent(text="Hello, world!"),
        )

        create_message_payload = {
            "jsonrpc": "2.0",
            "method": "sampling/createMessage",
            "id": 42,
            "params": {
                "messages": [sampling_message.model_dump(mode="json")],
                "maxTokens": 100,
            },
        }
        self.transport.queue_message(create_message_payload)

        await self.session.start()
        await asyncio.sleep(0.001)

        # Should get back an INTERNAL_ERROR response, not crash
        response_message = self.transport.sent_messages[-1].payload
        assert response_message["jsonrpc"] == "2.0"
        assert response_message["id"] == 42
        assert "error" in response_message
        assert response_message["error"]["code"] == INTERNAL_ERROR
        assert (
            "Something went wrong in user code!" in response_message["error"]["message"]
        )

        # Session should still be running
        assert self.session._running is True

        await self.session.stop()

    async def test_slow_create_message_handler_does_not_block_loop(self):
        self.session.capabilities.sampling = True
        self.session._initialized = True

        # Use events to control timing precisely
        handler_started = asyncio.Event()
        handler_can_continue = asyncio.Event()

        async def controlled_slow_handler(
            request: CreateMessageRequest,
        ) -> CreateMessageResult:
            handler_started.set()  # Signal that handler has started
            await (
                handler_can_continue.wait()
            )  # Wait for test to give permission to continue
            return CreateMessageResult(
                role="assistant",
                content=TextContent(text="slow response"),
                model="test-model",
                stop_reason="endTurn",
            )

        self.session.create_message_handler = controlled_slow_handler

        # Send slow request then fast request
        self.transport.queue_message(
            {
                "jsonrpc": "2.0",
                "method": "sampling/createMessage",
                "id": 1,
                "params": {
                    "messages": [
                        SamplingMessage(
                            role="user", content=TextContent(text="test")
                        ).model_dump(mode="json")
                    ],
                    "maxTokens": 100,
                },
            }
        )
        self.transport.queue_message({"jsonrpc": "2.0", "method": "ping", "id": 2})

        await self.session.start()

        # Wait for slow handler to start
        await handler_started.wait()

        # At this point, slow handler is running but blocked
        # The ping should still get processed
        await asyncio.sleep(0.01)  # Give message loop a chance to process ping

        ping_responses = [
            msg for msg in self.transport.sent_messages if msg.payload.get("id") == 2
        ]
        assert len(ping_responses) == 1, (
            "Ping should be processed while slow handler is blocked"
        )

        # Now let the slow handler finish
        handler_can_continue.set()
        await asyncio.sleep(0.01)
        assert len(self.transport.sent_messages) == 2, (
            f"Expected 2 responses, got {len(self.transport.sent_messages)}"
        )

        ping_responses = [
            msg for msg in self.transport.sent_messages if msg.payload.get("id") == 2
        ]
        slow_responses = [
            msg for msg in self.transport.sent_messages if msg.payload.get("id") == 1
        ]

        assert len(ping_responses) == 1, "Should have exactly one ping response"
        assert len(slow_responses) == 1, "Should have exactly one slow handler response"

        # Verify the ping response is correct
        ping_response = ping_responses[0].payload
        assert ping_response["result"] == {}

        # Verify the slow response is correct
        slow_response = slow_responses[0].payload
        assert "result" in slow_response
        assert slow_response["result"]["model"] == "test-model"


class TestClientSessionInitialization:
    @pytest.fixture(autouse=True)
    def setup_fixtures(self):
        self.transport = MockTransport()
        self.session = ClientSession(
            self.transport,
            client_info=Implementation(name="test-client", version="1.0.0"),
            capabilities=ClientCapabilities(),
        )

    async def wait_for_sent_request(self, method: str) -> None:
        """Wait for a request to be sent - simple test sync helper."""
        for _ in range(100):  # Max 100ms wait
            if any(
                msg.payload.get("method") == method
                for msg in self.transport.sent_messages
            ):
                return
            await asyncio.sleep(0.001)
        raise AssertionError(f"Request {method} never sent")

    async def test_initialize_performs_complete_handshake_and_returns_server_result(
        self,
    ):
        # Arrange: prepare server response
        server_result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"logging": {}},
            "serverInfo": {"name": "test-server", "version": "1.0.0"},
        }

        # Act
        init_task = asyncio.create_task(self.session.initialize())
        await self.wait_for_sent_request("initialize")

        # Now respond to the request
        self.transport.queue_response(request_id=0, result=server_result)
        result = await init_task

        # Assert: verify complete handshake sequence
        assert len(self.transport.sent_messages) == 2

        # First message should be InitializeRequest
        init_request = self.transport.sent_messages[0]
        assert init_request.payload["method"] == "initialize"
        assert init_request.payload["params"]["clientInfo"]["name"] == "test-client"
        assert init_request.payload["id"] == 0

        # Second message should be InitializedNotification
        init_notification = self.transport.sent_messages[1]
        assert init_notification.payload["method"] == "notifications/initialized"
        assert "id" not in init_notification.payload  # notifications have no id

        # Session should be marked as initialized
        assert self.session._initialized is True
        assert self.session._initialize_result is not None

        # Return value should be the server result
        assert result.protocol_version == PROTOCOL_VERSION
        assert result.server_info.name == "test-server"

    async def test_initialize_is_idempotent_and_returns_same_result_on_multiple_calls(
        self,
    ):
        # Arrange: prepare server response
        server_result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"logging": {}},
            "serverInfo": {"name": "test-server", "version": "1.0.0"},
        }

        # Act: start first initialization
        init_task = asyncio.create_task(self.session.initialize())
        await self.wait_for_sent_request("initialize")
        self.transport.queue_response(request_id=0, result=server_result)

        # Complete first initialization, then call again
        result1 = await init_task
        result2 = await self.session.initialize()
        result3 = await self.session.initialize()

        # Assert: handshake only happened once
        assert (
            len(self.transport.sent_messages) == 2
        )  # init request + notification only

        # All results should be identical
        assert result1 is result2 is result3
        assert result1.server_info.name == "test-server"

        # Session state should be consistent
        assert self.session._initialized is True
        assert self.session._initializing is None  # No ongoing initialization

    async def test_initialize_handles_concurrent_calls_and_returns_same_result(self):
        # Arrange: prepare server response
        server_result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"logging": {}},
            "serverInfo": {"name": "test-server", "version": "1.0.0"},
        }

        # Act: start multiple concurrent initialization calls
        task1 = asyncio.create_task(self.session.initialize())
        task2 = asyncio.create_task(self.session.initialize())
        task3 = asyncio.create_task(self.session.initialize())

        # Wait for the first request to be sent (only one should be sent)
        await self.wait_for_sent_request("initialize")

        # Respond to the single request
        self.transport.queue_response(request_id=0, result=server_result)

        # Wait for all tasks to complete
        result1, result2, result3 = await asyncio.gather(task1, task2, task3)

        # Assert: only one handshake happened
        assert (
            len(self.transport.sent_messages) == 2
        )  # init request + notification only
        assert self.session._request_id == 1  # only one request ID allocated

        # All results should be identical
        assert result1 is result2 is result3
        assert result1.server_info.name == "test-server"

        # Session should be properly initialized
        assert self.session._initialized is True
        assert self.session._initializing is None

        # Assert: pending request should be cleaned up
        assert len(self.session._pending_requests) == 0

    async def test_initialize_stops_session_and_raises_on_protocol_version_mismatch(
        self,
    ):
        # Arrange: prepare server response with wrong protocol version
        server_result = {
            "protocolVersion": "NOT_A_VERSION",
            "capabilities": {"logging": {}},
            "serverInfo": {"name": "test-server", "version": "1.0.0"},
        }

        # Act & Assert: initialization should fail
        init_task = asyncio.create_task(self.session.initialize())
        await self.wait_for_sent_request("initialize")
        self.transport.queue_response(request_id=0, result=server_result)

        with pytest.raises(ValueError, match="Protocol version mismatch"):
            await init_task

        # Assert: session should be cleanly stopped
        assert self.transport.closed is True
        assert self.session._running is False
        assert self.session._initialized is False
        assert self.session._initialize_result is None

        # Should have sent initialize request but no initialized notification
        assert len(self.transport.sent_messages) == 1
        assert self.transport.sent_messages[0].payload["method"] == "initialize"

        # Assert: pending request should be cleaned up
        assert len(self.session._pending_requests) == 0

    async def test_initialize_sends_cancelled_notification_and_stops_session_on_timeout(
        self,
    ):
        # Arrange: we'll start initialization but never respond

        # Act & Assert: initialization should timeout
        with pytest.raises(TimeoutError, match="Initialization timed out after 0.01s"):
            await self.session.initialize(timeout=0.01)

        # Assert: should have sent initialize request and cancelled notification
        assert len(self.transport.sent_messages) == 2

        init_request = self.transport.sent_messages[0]
        assert init_request.payload["method"] == "initialize"
        assert init_request.payload["id"] == 0

        cancelled_notification = self.transport.sent_messages[1]
        assert cancelled_notification.payload["method"] == "notifications/cancelled"
        assert cancelled_notification.payload["params"]["requestId"] == 0
        assert (
            cancelled_notification.payload["params"]["reason"]
            == "Initialization timed out"
        )
        assert "id" not in cancelled_notification.payload  # notifications have no id

        # Assert: session should be cleanly stopped
        assert self.transport.closed is True
        assert self.session._running is False
        assert self.session._initialized is False
        assert self.session._initialize_result is None

        # Assert: pending request should be cleaned up
        assert len(self.session._pending_requests) == 0
        assert self.session._request_id == 1  # request ID was allocated

    async def test_initialize_stops_session_and_reraises_on_transport_failure(self):
        # Arrange: make transport fail during send
        async def failing_send(payload, metadata=None):
            raise ConnectionError("Network connection lost")

        self.transport.send = failing_send

        # Act & Assert: initialization should fail with transport error
        with pytest.raises(ConnectionError, match="Network connection lost"):
            await self.session.initialize()

        # Assert: session should be cleanly stopped
        assert self.transport.closed is True
        assert self.session._running is False
        assert self.session._initialized is False
        assert self.session._initialize_result is None

        # Assert: no pending requests left behind
        assert len(self.session._pending_requests) == 0
        assert self.session._request_id == 1  # request ID was allocated before failure
