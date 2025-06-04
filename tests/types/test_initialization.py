"""
Test initialization-related types.
"""

from mcp.new_types import (
    PROTOCOL_VERSION,
    ClientCapabilities,
    Implementation,
    InitializedNotification,
    InitializeRequest,
    InitializeResult,
    ServerCapabilities,
)


class TestInitialization:
    def test_initialize_request_roundtrip(self):
        request = InitializeRequest(
            clientInfo=Implementation(name="Test client", version="1"),
            capabilities=ClientCapabilities(),
            protocol_version=PROTOCOL_VERSION,
        )
        protocol_data = request.to_protocol()
        reconstructed = InitializeRequest.from_protocol(protocol_data)
        assert reconstructed == request
        assert reconstructed.client_info.name == "Test client"

    def test_initialized_notification_roundtrip(self):
        notif = InitializedNotification()
        protocol_data = notif.to_protocol()
        reconstructed = InitializedNotification.from_protocol(protocol_data)
        assert reconstructed == notif

    def test_initialize_result_roundtrip(self):
        result = InitializeResult(
            protocol_version="2025-03-26",
            capabilities=ServerCapabilities(),
            server_info=Implementation(name="test_server", version="1.0"),
        )
        protocol_data = result.to_protocol()
        print("protocol_data", protocol_data)
        print("result", result)
        reconstructed = InitializeResult.from_protocol(protocol_data)
        print("-" * 100)
        print("reconstructed", reconstructed)
        assert reconstructed == result

    def test_initialize_result_with_metadata_roundtrips(self):
        protocol_data = {
            "protocolVersion": "not_a_version",
            "capabilities": {},
            "serverInfo": {"name": "test_server", "version": "1.0"},
            "_meta": {"some": "metadata"},
        }
        result = InitializeResult.from_protocol(protocol_data)
        assert result.metadata == {"some": "metadata"}
        serialized = result.to_protocol()
        assert serialized == protocol_data

    def test_initialize_result_ignores_empty_metadata_from_protocol(self):
        protocol_data = {
            "protocolVersion": "not_a_version",
            "capabilities": {},
            "serverInfo": {"name": "test_server", "version": "1.0"},
            "_meta": {},
        }
        result = InitializeResult.from_protocol(protocol_data)
        assert result.metadata is None
        serialized = result.to_protocol()
        assert "_meta" not in serialized

    def test_initialize_result_does_not_serialize_metadata_if_empty(self):
        result = InitializeResult(
            protocol_version="not_a_version",
            capabilities=ServerCapabilities(),
            server_info=Implementation(name="test_server", version="1.0"),
        )
        serialized = result.to_protocol()
        assert "_meta" not in serialized
