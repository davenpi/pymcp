import asyncio
from typing import Any

from mcp.transport.base import Transport, TransportMessage


class MockTransport(Transport):
    """Mock transport for testing."""

    def __init__(self):
        self.sent_messages: list[TransportMessage] = []
        self.incoming_queue: asyncio.Queue[TransportMessage] = asyncio.Queue()
        self.closed = False

    def queue_message(
        self, payload: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> None:
        """Queue a message to be received."""
        message = TransportMessage(payload=payload, metadata=metadata)
        self.incoming_queue.put_nowait(message)

    def queue_response(
        self, request_id: int, result: Any = None, error: dict | None = None
    ) -> None:
        """Helper: queue a JSON-RPC response."""
        payload = {"jsonrpc": "2.0", "id": request_id}
        if error:
            payload["error"] = error
        else:
            payload["result"] = result
        self.queue_message(payload)

    async def send(
        self, payload: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> None:
        if self.closed:
            raise ConnectionError("Transport closed")
        self.sent_messages.append(TransportMessage(payload=payload, metadata=metadata))

    async def receive(self) -> TransportMessage:
        if self.closed:
            raise ConnectionError("Transport closed")
        return await self.incoming_queue.get()

    async def close(self) -> None:
        self.closed = True


async def test_mock_transport():
    """Test the mock transport works."""
    print("Testing mock transport...")

    transport = MockTransport()

    # Test send
    await transport.send({"method": "test"}, {"auth": "token"})
    assert len(transport.sent_messages) == 1
    assert transport.sent_messages[0].payload["method"] == "test"  # Now .payload
    assert transport.sent_messages[0].metadata["auth"] == "token"  # And .metadata
    print("✅ Send works")

    # Test receive
    transport.queue_message({"result": "success"})
    message = await transport.receive()
    assert message.payload["result"] == "success"
    print("✅ Receive works")

    # Test the helper
    transport.queue_response(request_id=123, result={"data": "test"})
    response = await transport.receive()
    assert response.payload["id"] == 123
    assert response.payload["result"]["data"] == "test"
    print("✅ Response helper works")

    # Test context manager
    async with MockTransport() as t:
        await t.send({"test": True})
    assert t.closed
    print("✅ Context manager works")

    print("🎉 Mock transport is working!")


if __name__ == "__main__":
    asyncio.run(test_mock_transport())
