import asyncio

import pytest
from mock_transport import MockTransport

from mcp.client.new_session import ClientSession
from mcp.protocol import InitializeRequest
from mcp.protocol.base import PROTOCOL_VERSION
from mcp.protocol.initialization import Implementation


def create_test_request():
    """Helper to create a standard test request."""
    return InitializeRequest(
        protocolVersion=PROTOCOL_VERSION,
        client_info=Implementation(name="test-client", version="1.0.0"),
    )


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

    result = await session.request(request)

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


async def test_error_response():
    """Test error handling."""
    transport = MockTransport()
    session = ClientSession(transport)

    transport.queue_response(
        request_id=0, error={"code": -32600, "message": "Invalid Request"}
    )

    request = create_test_request()

    with pytest.raises(Exception, match="RPC Error"):
        await session.request(request)

    await session.stop()


async def test_simple_correlation():
    """Test basic request/response correlation."""
    transport = MockTransport()
    session = ClientSession(transport)

    req = create_test_request()

    # Queue ONE response
    transport.queue_response(request_id=0, result="my_result")

    # Make ONE request
    result = await session.request(req)

    # Verify it worked
    assert result == "my_result"
    await session.stop()


async def test_wrong_id_ignored():
    """Test that responses with wrong IDs are ignored."""
    transport = MockTransport()
    session = ClientSession(transport)

    req = create_test_request()

    # Queue response with WRONG ID
    transport.queue_response(request_id=999, result="wrong")

    # Queue response with CORRECT ID
    transport.queue_response(request_id=0, result="correct")

    # Make request - should get "correct", not "wrong"
    result = await session.request(req)
    assert result == "correct"
    await session.stop()


async def test_request_timeout():
    """Test that requests don't hang forever if no response comes."""
    transport = MockTransport()
    session = ClientSession(transport)

    # Don't queue any response - request should timeout
    request = create_test_request()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(session.request(request), timeout=0.1)

    await session.stop()


async def test_session_lifecycle():
    """Test starting and stopping session."""
    transport = MockTransport()
    session = ClientSession(transport)

    # Session should auto-start on first request
    assert not session._running

    transport.queue_response(request_id=0, result="test")
    await session.request(create_test_request())

    assert session._running

    await session.stop()
    assert not session._running


if __name__ == "__main__":
    asyncio.run(test_basic_request_response())
    asyncio.run(test_error_response())
    asyncio.run(test_wrong_id_ignored())
    asyncio.run(test_simple_correlation())
    asyncio.run(test_request_timeout())
    asyncio.run(test_session_lifecycle())
