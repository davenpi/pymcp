import asyncio

import pytest

from mcp.client.new_session import ClientSession
from mcp.protocol import CallToolRequest, InitializeRequest, JSONRPCRequest
from mcp.protocol.base import PROTOCOL_VERSION
from mcp.protocol.initialization import ClientCapabilities, Implementation
from tests.new_client.mock_transport import MockTransport


def create_test_request():
    """Helper to create a standard test request."""
    return InitializeRequest(
        protocolVersion=PROTOCOL_VERSION,
        client_info=Implementation(name="test-client", version="1.0.0"),
    )


class TestClientSessionBasics:
    @pytest.fixture(autouse=True)
    async def setup_session(self):
        self.transport = MockTransport()
        self.session = ClientSession(
            self.transport,
            client_info=Implementation(name="test-client", version="1.0.0"),
            capabilities=ClientCapabilities(),
        )
        yield
        await self.session.stop()

    async def test_session_lifecycle(self):
        """Test starting and stopping session."""

        # Session should auto-start on first request
        assert not self.session._running

        self.transport.queue_response(request_id=0, result="test")
        _, _ = await self.session.send_request(create_test_request())

        assert self.session._running

        await self.session.stop()
        assert not self.session._running

    async def test_simple_correlation(self):
        """Test basic request/response correlation."""

        # Queue ONE response
        self.transport.queue_response(request_id=0, result="my_result")

        # Make ONE request
        result, _ = await self.session.send_request(create_test_request())

        # Verify it worked
        assert result == "my_result"
        await self.session.stop()
        assert not self.session._running

    async def test_session_message_loop_processes_queued_responses(self):
        """Test that the message loop processes responses."""
        # Start session manually
        await self.session.start()

        # Queue a response
        self.transport.queue_response(0, {"result": "test"})

        # Create a request manually
        request = CallToolRequest(name="test")
        request_id = self.session._request_id
        self.session._request_id += 1

        # Set up pending request tracking
        future = asyncio.Future()
        self.session._pending_requests[request_id] = future

        # Send the request (this should trigger the response processing)
        jsonrpc_request = JSONRPCRequest.from_request(request, request_id)
        await self.transport.send(jsonrpc_request.to_wire())

        # Wait a moment for message loop to process
        await asyncio.sleep(0.01)

        # Check if future was resolved
        assert future.done()
        result, metadata = future.result()
        assert result == {"result": "test"}

    async def test_fresh_state_between_tests(self):
        """Verify we get fresh state for each test."""
        print(f"Request ID: {self.session._request_id}")
        print(f"Pending requests: {len(self.session._pending_requests)}")
        print(f"Transport queue size: {self.transport.incoming_queue.qsize()}")
        print(f"Sent messages: {len(self.transport.sent_messages)}")

        # This should all be clean state
        assert self.session._request_id == 0
        assert len(self.session._pending_requests) == 0
        assert self.transport.incoming_queue.qsize() == 0
        assert len(self.transport.sent_messages) == 0

    async def test_debug_send_request(self):
        transport = MockTransport()
        session = ClientSession(
            transport,
            client_info=Implementation(name="test-client", version="1.0.0"),
            capabilities=ClientCapabilities(),
        )

        try:
            print("Queuing response...")
            transport.queue_response(0, {"result": "test"})
            print(f"Queue size after queuing: {transport.incoming_queue.qsize()}")

            print("Creating request...")
            request = CallToolRequest(name="tool1")

            print("Calling send_request...")
            result, metadata = await session.send_request(request)
            print(f"Got result: {result}")
            assert result == {"result": "test"}

        finally:
            await session.stop()

    # async def test_two_sequential_requests_work(self):
    #     """Test that multiple requests in sequence work correctly."""
    #     transport = MockTransport()
    #     session = ClientSession(transport)

    #     try:
    #         # Queue responses for two requests
    #         transport.queue_response(0, {"result": "first"})
    #         transport.queue_response(1, {"result": "second"})

    #         # Send two requests in sequence
    #         request1 = CallToolRequest(name="tool1")
    #         request2 = CallToolRequest(name="tool2")

    #         result1, _ = await session.send_request(request1)
    #         result2, _ = await session.send_request(request2)

    #         # Verify both worked
    #         assert result1 == {"result": "first"}
    #         assert result2 == {"result": "second"}

    #         # Verify request IDs were incremented correctly
    #         assert len(transport.sent_messages) == 2
    #         assert transport.sent_messages[0].payload["id"] == 0
    #         assert transport.sent_messages[1].payload["id"] == 1

    #     finally:
    #         await session.stop()

    async def test_two_requests_with_proper_timing(self):
        transport = MockTransport()
        session = ClientSession(
            transport,
            client_info=Implementation(name="test-client", version="1.0.0"),
            capabilities=ClientCapabilities(),
        )

        try:
            # Send first request, queue its response
            transport.queue_response(0, {"result": "first"})
            request1 = CallToolRequest(name="tool1")
            result1, _ = await session.send_request(request1)

            # Send second request, queue its response
            transport.queue_response(1, {"result": "second"})
            request2 = CallToolRequest(name="tool2")
            result2, _ = await session.send_request(request2)

            assert result1 == {"result": "first"}
            assert result2 == {"result": "second"}

        finally:
            await session.stop()


# class TestClientSessionSampling:
#     async def test_routes_create_message_to_handler_when_sampling_enabled(self):
#         pass

#     async def test_returns_error_when_create_message_but_sampling_disabled(self):
#         pass

#     async def test_returns_error_when_create_message_but_no_handler(self):
#         pass

#     async def test_routes_list_roots_to_default_handler(self):
#         pass

#     async def test_returns_error_when_list_roots_but_capability_disabled(self):
#         pass
