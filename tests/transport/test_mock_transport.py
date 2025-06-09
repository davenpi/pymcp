import asyncio
from typing import Any

from mcp.transport.base import Transport, TransportMessage


class MockTransport(Transport):
    """Mock transport for testing."""

    def __init__(self):
        self.sent_messages: list[dict] = []
        self.incoming_queue: asyncio.Queue[TransportMessage] = asyncio.Queue()
        self.closed = False

    def queue_message(
        self, payload: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> None:
        """Queue a message to be received."""
        message = TransportMessage(payload=payload, metadata=metadata)
        self.incoming_queue.put_nowait(message)

    async def send(
        self, payload: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> None:
        if self.closed:
            raise ConnectionError("Transport closed")
        self.sent_messages.append({"payload": payload, "metadata": metadata})

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
    assert transport.sent_messages[0]["payload"]["method"] == "test"
    print("✅ Send works")

    # Test receive
    transport.queue_message({"result": "success"})
    message = await transport.receive()
    assert message.payload["result"] == "success"
    print("✅ Receive works")

    # Test context manager
    async with MockTransport() as t:
        await t.send({"test": True})
    assert t.closed
    print("✅ Context manager works")

    print("🎉 Mock transport is working!")


if __name__ == "__main__":
    asyncio.run(test_mock_transport())
