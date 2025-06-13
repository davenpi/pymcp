from unittest.mock import AsyncMock

import pytest

from mcp.protocol.common import PingRequest

from .conftest import BaseSessionTest


class TestClientSessionLifecycle(BaseSessionTest):
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
