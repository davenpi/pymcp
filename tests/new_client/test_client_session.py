import asyncio
from unittest.mock import AsyncMock

import pytest

from mcp.client.new_session import ClientSession
from mcp.protocol.common import CancelledNotification, PingRequest
from mcp.protocol.initialization import ClientCapabilities, Implementation
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

        # Give the message loop time to process both messages
        await asyncio.sleep(0.1)

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
