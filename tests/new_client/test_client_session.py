from unittest.mock import AsyncMock

import pytest

from mcp.client.new_session import ClientSession
from mcp.protocol.initialization import ClientCapabilities, Implementation
from tests.new_client.mock_transport import MockTransport


class TestClientLifecycle:
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
