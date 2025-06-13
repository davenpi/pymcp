import asyncio

import pytest

from mcp.protocol.base import PROTOCOL_VERSION

from .conftest import BaseSessionTest


class TestClientSessionInitialization(BaseSessionTest):
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

    async def test_initialize_raises_timeout_error_and_stops_session_on_timeout(
        self,
    ):
        # Arrange: we'll start initialization but never respond

        # Act & Assert: initialization should timeout
        with pytest.raises(TimeoutError, match="Initialization timed out after 0.01s"):
            await self.session.initialize(timeout=0.01)

        # Assert: should have sent initialize request
        assert len(self.transport.sent_messages) == 1

        init_request = self.transport.sent_messages[0]
        assert init_request.payload["method"] == "initialize"
        assert init_request.payload["id"] == 0

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
