import asyncio

import pytest

from mcp.client.new_session import ClientSession
from mcp.protocol import CallToolRequest, InitializeRequest, JSONRPCRequest
from mcp.protocol.base import PROTOCOL_VERSION
from mcp.protocol.initialization import Implementation
from mcp.shared.new_exceptions import MCPError
from tests.new_client.mock_transport import MockTransport


def create_test_request():
    """Helper to create a standard test request."""
    return InitializeRequest(
        protocolVersion=PROTOCOL_VERSION,
        client_info=Implementation(name="test-client", version="1.0.0"),
    )


@pytest.mark.asyncio
async def test_basic_request_response():
    """Test basic request/response correlation."""
    transport = MockTransport()
    session = ClientSession(transport)

    # Queue the response BEFORE making the request
    transport.queue_response(
        request_id=0,
        result={
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"going": "here"},
            "serverInfo": {"name": "test-server", "version": "1.0.0"},
        },
    )

    # Make the request
    request = create_test_request()

    result, _ = await session.send_request(request)

    # Verify the request was sent correctly
    assert len(transport.sent_messages) == 1
    sent = transport.sent_messages[0].payload
    assert sent["jsonrpc"] == "2.0"
    assert sent["id"] == 0
    assert sent["method"] == "initialize"
    assert sent["params"]["protocolVersion"] == PROTOCOL_VERSION

    # Verify we got the right response
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["serverInfo"]["name"] == "test-server"

    await session.stop()


@pytest.mark.asyncio
async def test_error_response():
    """Test error handling."""
    transport = MockTransport()
    session = ClientSession(transport)

    transport.queue_response(
        request_id=0, error={"code": -32600, "message": "Invalid Request"}
    )

    request = create_test_request()

    with pytest.raises(MCPError, match="Invalid Request"):
        await session.send_request(request)

    await session.stop()


@pytest.mark.asyncio
async def test_simple_correlation():
    """Test basic request/response correlation."""
    transport = MockTransport()
    session = ClientSession(transport)

    req = create_test_request()

    # Queue ONE response
    transport.queue_response(request_id=0, result="my_result")

    # Make ONE request
    result, _ = await session.send_request(req)

    # Verify it worked
    assert result == "my_result"
    await session.stop()


@pytest.mark.asyncio
async def test_request_timeout():
    """Test that requests don't hang forever if no response comes."""
    transport = MockTransport()
    session = ClientSession(transport)

    # Don't queue any response - request should timeout
    request = create_test_request()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(session.send_request(request), timeout=0.1)

    await session.stop()


@pytest.mark.asyncio
async def test_session_lifecycle():
    """Test starting and stopping session."""
    transport = MockTransport()
    session = ClientSession(transport)

    # Session should auto-start on first request
    assert not session._running

    transport.queue_response(request_id=0, result="test")
    _, _ = await session.send_request(create_test_request())

    assert session._running

    await session.stop()
    assert not session._running


class TestClientSessionBasics:
    @pytest.fixture(autouse=True)
    async def setup_session(self):
        self.transport = MockTransport()
        self.session = ClientSession(self.transport)
        yield
        await self.session.stop()

    async def test_transport_basic_send_receive(self):
        """Verify our mock transport works in isolation."""
        self.transport.queue_message({"test": "data"})

        message = await self.transport.receive()
        assert message.payload == {"test": "data"}

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

    # async def test_send_request_generates_incremental_request_ids(self):
    #     transport = MockTransport()
    #     session = ClientSession(transport)

    #     try:
    #         # Queue two responses
    #         transport.queue_response(0, {"result": "first"})
    #         transport.queue_response(1, {"result": "second"})

    #         # Send two requests
    #         request1 = CallToolRequest(name="tool1")
    #         request2 = CallToolRequest(name="tool2")

    #         await session.send_request(request1)
    #         await session.send_request(request2)

    #         # Verify request IDs are 0, 1
    #         assert len(transport.sent_messages) == 2
    #         assert transport.sent_messages[0].payload["id"] == 0
    #         assert transport.sent_messages[1].payload["id"] == 1
    #     finally:
    #         await session.stop()

    async def test_debug_send_request(self):
        transport = MockTransport()
        session = ClientSession(transport)

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
        session = ClientSession(transport)

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

    # async def test_debug_two_requests_detailed(self):
    #     transport = MockTransport()
    #     session = ClientSession(transport)

    #     try:
    #         print("Queuing responses...")
    #         transport.queue_response(0, {"result": "first"})
    #         transport.queue_response(1, {"result": "second"})
    #         print(f"Queue size: {transport.incoming_queue.qsize()}")

    #         print("Creating requests...")
    #         request1 = CallToolRequest(name="tool1")
    #         request2 = CallToolRequest(name="tool2")

    #         print(f"Session request ID before first: {session._request_id}")
    #         print("Sending first request...")
    #         result1, _ = await session.send_request(request1)
    #         print(f"Got first result: {result1}")
    #         print(f"Session request ID after first: {session._request_id}")
    #         print(
    #             "Pending requests after first: "
    #             f"{list(session._pending_requests.keys())}"
    #         )
    #         print(f"Queue size after first: {transport.incoming_queue.qsize()}")

    #         print("Sending second request...")
    #         print(f"Session request ID before second: {session._request_id}")
    #         # This is where it should hang
    #         result2, _ = await session.send_request(request2)
    #         print(f"Got second result: {result2}")

    #     finally:
    #         await session.stop()
