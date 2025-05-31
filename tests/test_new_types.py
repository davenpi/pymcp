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

import pytest
from pydantic import ValidationError

from mcp.new_types import (
    ClientCapabilities,
    Implementation,
    InitializeRequest,
    Request,
    RootsCapability,
)


class TestRequestSerialization:
    def test_request_roundtrip(self):
        original = Request(
            method="test",
            progress_token="123",
        )
        wire = original.to_wire()
        reconstructed = Request.from_wire(wire)
        assert reconstructed == original

    def test_initialize_request_roundtrip(self):
        original = InitializeRequest(
            progress_token="123",
            protocol_version="2025-03-26",
            client_info=Implementation(name="test_client", version="1.0"),
            capabilities=ClientCapabilities(roots=RootsCapability(list_changed=True)),
        )
        wire = original.to_wire()
        reconstructed = InitializeRequest.from_wire(wire)
        assert reconstructed == original

    def test_from_wire_invalid_data(self):
        with pytest.raises(ValidationError):
            # Missing required fields e.g., protocolVersion
            InitializeRequest.from_wire({"method": "initialize"})


class TestWireFormatCompliance:
    # Making sure the JSON-RPC envelope is correct
    def test_jsonrpc_request_envelope(self):
        pass

    def test_jsonrpc_notification_envelope(self):
        pass

    def test_jsonrpc_response_envelope(self):
        pass


class TestInitializationFlow:
    # All initialization-related types together
    def test_initialize_request(self):
        pass

    def test_initialized_notification(self):
        pass

    def test_client_capabilities_structure(self):
        pass


class TestToolsFlow:
    # All tools-related types together
    def test_list_tools_request(self):
        pass

    def test_list_tools_response(self):
        pass

    def test_call_tool_request(self):
        pass

    def test_call_tool_response(self):
        pass

    def test_tool_progress_notification(self):  # Progress within tools context
        pass
