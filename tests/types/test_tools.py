"""
Test tool-related types.
"""

from mcp.new_types import ListToolsRequest, ProgressNotification


class TestTools:

    def test_call_tool_with_arguments(self):
        # Test the complex case with nested data
        pass

    def test_invalid_wire_data(self):
        # Missing fields, wrong types, etc.
        pass

    def test_list_tools_request_minimal(self):
        # Test with no optional fields
        request = ListToolsRequest()
        protocol_data = request.to_protocol()
        reconstructed = ListToolsRequest.from_protocol(protocol_data)
        assert reconstructed == request
        assert reconstructed.cursor is None
        assert reconstructed.progress_token is None
        assert reconstructed.method == "tools/list"

    def test_list_tools_from_protocol_with_no_data_roundtrips_to_method_only(self):
        protocol_data = {"method": "tools/list"}
        request = ListToolsRequest.from_protocol(protocol_data)
        assert request.method == "tools/list"
        assert request.cursor is None
        assert request.progress_token is None
        assert request.to_protocol() == protocol_data

    def test_list_tools_request_round_trip_with_cursor_and_progress_token(self):
        request = ListToolsRequest(
            cursor="123",
            progress_token="456",
        )
        protocol_data = request.to_protocol()
        reconstructed = ListToolsRequest.from_protocol(protocol_data)
        assert reconstructed == request
        assert reconstructed.cursor == "123"
        assert reconstructed.progress_token == "456"
        assert reconstructed.method == "tools/list"

    def test_list_tools_request_wire_format(self):
        # Verify JSON matches spec exactly
        pass

    def test_progress_notification_roundtrip_without_metadata(self):
        protocol_data = {
            "method": "notifications/progress",
            "params": {
                "progressToken": "progress_token",
                "progress": 0.5,
                "total": 100,
                "message": "test",
            },
        }
        notif = ProgressNotification.from_protocol(protocol_data)
        assert notif.method == "notifications/progress"
        assert notif.progress_token == "progress_token"
        assert notif.progress == 0.5
        assert notif.total == 100
        assert notif.message == "test"
        serialized = notif.to_protocol()
        assert serialized == protocol_data

    def test_progress_notification_roundtrip_with_metadata(self):
        """Test that metadata is preserved during roundtrip"""
        protocol_data = {
            "method": "notifications/progress",
            "params": {
                "progressToken": "progress_token",
                "progress": 0.5,
                "total": 100,
                "message": "test",
                "_meta": {
                    "requestId": "req-123",
                    "timestamp": "2025-06-04T10:00:00Z",
                    "customField": {"nested": "value"},
                },
            },
        }

        # Deserialize
        notif = ProgressNotification.from_protocol(protocol_data)
        assert notif.metadata == {
            "requestId": "req-123",
            "timestamp": "2025-06-04T10:00:00Z",
            "customField": {"nested": "value"},
        }

        # Serialize back
        serialized = notif.to_protocol()
        assert serialized == protocol_data

    def test_progress_notification_ignores_empty_metadata(self):
        """Test handling of empty _meta object"""
        protocol_data = {
            "method": "notifications/progress",
            "params": {
                "progressToken": "progress_token",
                "progress": 0.5,
                "total": 100,
                "_meta": {},
            },
        }

        notif = ProgressNotification.from_protocol(protocol_data)
        assert notif.metadata is None

        serialized = notif.to_protocol()
        assert "_meta" not in serialized["params"]
