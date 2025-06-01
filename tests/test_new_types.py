"""
Test the fundamental types in a way that logically groups related types together.
For example, test initialization-related types together, tools-related types together,
etc.

We want to test:

1. Round-trip - proving that serializing and deserializing the types works
2. Wire format compliance - proving spec adherence
3. Edges cases - proving robustness
4. Type safety - proving error handling works and developer experience is seamless
"""

import copy

import pytest
from pydantic import ValidationError

from mcp.new_types import (
    ClientCapabilities,
    Implementation,
    InitializeRequest,
    InitializeResult,
    JSONRPCRequest,
    ListToolsRequest,
    Notification,
    Request,
    RootsCapability,
    ServerCapabilities,
)


class TestRequestSerialization:
    def test_request_roundtrip(self):
        original = Request(
            method="test",
            progress_token="123",
        )
        wire = original.to_protocol()
        reconstructed = Request.from_protocol(wire)
        assert reconstructed == original

    def test_initialize_request_roundtrip(self):
        original = InitializeRequest(
            progress_token="123",
            protocol_version="2025-03-26",
            client_info=Implementation(name="test_client", version="1.0"),
            capabilities=ClientCapabilities(roots=RootsCapability(list_changed=True)),
        )
        wire = original.to_protocol()
        reconstructed = InitializeRequest.from_protocol(wire)
        assert reconstructed == original

    def test_from_wire_missing_fields(self):
        with pytest.raises(ValidationError):
            # Missing required fields e.g., protocolVersion
            InitializeRequest.from_protocol({"method": "initialize"})

    def test_from_wire_missing_method(self):
        with pytest.raises(ValueError):
            InitializeRequest.from_protocol({"not_method": "initialize"})

    def test_from_wire_side_effect_free(self):
        """Make sure that the from_wire method does not mutate the input data"""
        data = {
            "method": "test",
            "params": {"arg1": "testing", "_meta": {"progressToken": "123"}},
        }
        original_data = copy.deepcopy(data)
        _ = Request.from_protocol(data)
        assert data == original_data


class TestNotificationSerialization:
    def test_notification_roundtrip(self):
        original = Notification(
            method="test",
            params={"arg1": "testing"},
        )
        wire = original.to_protocol()
        reconstructed = Notification.from_protocol(wire)
        assert reconstructed == original

    def test_from_wire_invalid_data(self):
        with pytest.raises(ValueError):
            Notification.from_protocol({"not_method": "test"})

    def test_from_wire_side_effect_free(self):
        data = {
            "method": "test",
            "params": {"arg1": "testing"},
            "_meta": {"progressToken": "123"},
        }
        original_data = copy.deepcopy(data)
        _ = Notification.from_protocol(data)
        assert data == original_data


class TestWireFormatCompliance:
    # Making sure the JSON-RPC envelope is correct
    def test_jsonrpc_request_envelope(self):
        pass

    def test_jsonrpc_notification_envelope(self):
        pass

    def test_jsonrpc_response_envelope(self):
        pass


class TestInitialization:
    # All initialization-related types together

    def test_initialize_request_full_stack(self):
        # Create the high-level request
        request = InitializeRequest(
            client_info=Implementation(name="test", version="1.0"),
            capabilities=ClientCapabilities(),
        )

        # Wrap in JSON-RPC envelope
        jsonrpc_request = JSONRPCRequest.from_request(request, id="1")

        # Serialize to wire
        wire_data = jsonrpc_request.to_wire()

        # Verify JSON-RPC structure
        assert wire_data["jsonrpc"] == "2.0"
        assert wire_data["id"] == "1"
        assert wire_data["method"] == "initialize"

        # Round-trip back
        reconstructed = JSONRPCRequest.model_validate(wire_data)
        original_request = reconstructed.to_request(InitializeRequest)

        assert original_request.client_info.name == "test"

    def test_initialize_request(self):
        pass

    def test_initialized_notification(self):
        pass

    def test_initialize_result_roundtrip(self):
        result = InitializeResult(
            protocol_version="2025-03-26",
            capabilities=ServerCapabilities(),
            server_info=Implementation(name="test_server", version="1.0"),
        )
        protocol_data = result.to_protocol()
        reconstructed = InitializeResult.from_protocol(protocol_data)
        assert reconstructed == result
        assert reconstructed.protocol_version == "2025-03-26"
        assert reconstructed.capabilities is not None
        assert reconstructed.server_info.name == "test_server"
        assert reconstructed.server_info.version == "1.0"
        assert reconstructed.instructions is None


class TestTools:
    def test_list_tools_wire_format(self):
        # Verify JSON matches spec exactly
        pass

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

    def test_list_tools_request_round_trip(self):
        # Happy path: object → protocol → object
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
