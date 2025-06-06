"""
Test miscellaneous types like Pings, CancelledNotifications, etc.
"""

import pytest

from mcp.new_types import CancelledNotification, PingRequest


class TestMisc:
    def test_ping_rejects_non_ping_request(self):
        with pytest.raises(ValueError):
            protocol_data = {"method": "not_ping"}
            _ = PingRequest.from_protocol(protocol_data)

    def test_ping_roundtrips(self):
        protocol_data = {"method": "ping"}
        ping = PingRequest.from_protocol(protocol_data)
        serialized = ping.to_protocol()
        assert serialized == protocol_data

    def test_cancelled_notification_roundtrips_with_id_alias(self):
        protocol_data = {
            "method": "notifications/cancelled",
            "params": {"requestId": 1, "reason": "no need"},
        }
        notif = CancelledNotification.from_protocol(protocol_data)
        assert notif.method == "notifications/cancelled"
        assert notif.request_id == 1
        assert notif.reason == "no need"
        serialized = notif.to_protocol()
        assert serialized == protocol_data
