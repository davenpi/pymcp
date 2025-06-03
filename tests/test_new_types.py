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
    JSONRPC_VERSION,
    PROTOCOL_VERSION,
    Annotations,
    CancelledNotification,
    ClientCapabilities,
    Error,
    Implementation,
    InitializeRequest,
    InitializeResult,
    JSONRPCError,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    ListResourcesRequest,
    ListToolsRequest,
    Notification,
    Ping,
    ProgressNotification,
    Request,
    Resource,
    Result,
    ServerCapabilities,
)


class TestSerialization:
    """
    Serialization is when we convert our types to dicts.
    Deserialization is when we convert dicts into our types.
    """

    def test_request_rejects_missing_method(self):
        with pytest.raises(ValidationError):
            _ = Request(progress_token="progressing")

    def test_request_gets_progress_token_from_data(self):
        protocol_data = {"method": "test", "params": {"_meta": {"progressToken": 1}}}
        req = Request.from_protocol(protocol_data)
        assert req.method == "test"
        assert req.progress_token == 1

    def test_request_serialization_does_not_mutate_input(self):
        protocol_data = {
            "method": "test",
            "params": {"_meta": {"progressToken": "123"}},
        }
        original_data = copy.deepcopy(protocol_data)
        req = Request.from_protocol(protocol_data)
        serialized = req.to_protocol()
        assert req.method == "test"
        assert req.progress_token == "123"
        assert serialized == original_data
        assert protocol_data == original_data

    def test_request_ignores_params_if_no_progress_token_metadata(self):
        protocol_data = {
            "method": "req",
            "params": {"testing": "hi", "_meta": {"not_a_progress_token": "not"}},
        }
        req = Request.from_protocol(protocol_data)
        serialized = req.to_protocol()
        assert serialized["method"] == "req"
        assert "params" not in serialized

    def test_request_converts_snake_case_to_camelCase_output(self):
        req = Request(
            method="test",
            progress_token="123",
        )
        serialized = req.to_protocol()
        assert serialized["method"] == "test"
        assert serialized["params"]["_meta"]["progressToken"] == "123"

    def test_request_ignores_unknown_fields_without_error(self):
        protocol_data = {
            "method": "test",
            "params": {"unknown": "test"},
        }
        req = Request.from_protocol(protocol_data)
        assert req.method == "test"

    def test_request_preserves_progress_token_roundtrip(self):
        request = Request(
            method="test",
            progress_token="123",
        )
        protocol_data = request.to_protocol()
        assert protocol_data["params"]["_meta"]["progressToken"] == "123"
        reconstructed = Request.from_protocol(protocol_data)
        assert reconstructed.progress_token == "123"
        assert reconstructed.method == "test"

    def test_notification_rejects_missing_method(self):
        with pytest.raises(KeyError):
            Notification.from_protocol({"not_method": "test"})

    def test_notification_serialization_does_not_mutate_input(self):
        protocol_data = {
            "method": "notification/test",
        }
        original_data = copy.deepcopy(protocol_data)
        notif = Notification.from_protocol(protocol_data)
        serialized = notif.to_protocol()
        assert serialized == original_data
        assert protocol_data == original_data

    def test_can_initialize_empty_result(self):
        res = Result()
        assert res is not None

    def test_result_serialization_not_implemented(self):
        protocol_data = {
            "test": "result",
        }
        with pytest.raises(NotImplementedError):
            Result.from_protocol(protocol_data)

    def test_error_rejects_missing_code(self):
        with pytest.raises(KeyError):
            Error.from_protocol({"message": "test"})

    def test_error_rejects_non_integer_code(self):
        with pytest.raises(ValidationError):
            Error.from_protocol({"code": "not_an_int", "message": "test"})

    def test_error_rejects_missing_message(self):
        with pytest.raises(KeyError):
            Error.from_protocol({"code": -1, "data": "test"})

    def test_error_rejects_int_data(self):
        with pytest.raises(ValidationError):
            Error.from_protocol({"code": -1, "message": "test", "data": 1})

    def test_error_preserves_nested_dict_data_roundtrip(self):
        data = {"code": -1, "message": "test", "data": {"field": "email"}}
        err = Error.from_protocol(data)
        assert err.to_protocol() == data

    def test_error_accepts_exceptions_in_constructor(self):
        err = Error(code=-1, message="test", data=ValueError("test error"))
        result = err.to_protocol()
        assert isinstance(result["data"], str)
        print(result["data"])
        assert "ValueError" in result["data"]
        assert "test error" in result["data"]

    def test_error_accepts_exception_in_protocol_data(self):
        data = {"code": -1, "message": "test", "data": ValueError("test error")}
        err = Error.from_protocol(data)
        assert isinstance(err.data, str)
        assert "ValueError" in err.data
        assert "test error" in err.data

    def test_error_preserves_empty_string_data(self):
        err = Error(code=-1, message="test", data="")
        result = err.to_protocol()
        assert result["data"] == ""

    def test_error_preserves_empty_dict_data(self):
        err = Error(code=-1, message="test", data={})
        result = err.to_protocol()
        assert result["data"] == {}

    def test_error_captures_exception_chain(self):
        try:
            try:
                raise ValueError("inner")
            except ValueError as e:
                raise RuntimeError("outer") from e
        except RuntimeError as exc:
            err = Error(code=-1, message="test", data=exc)
            result = err.to_protocol()
            assert "direct cause" in result["data"] or "caused by" in result["data"]
            assert "ValueError" in result["data"]
            assert "inner" in result["data"]
            assert "RuntimeError" in result["data"]
            assert "outer" in result["data"]

    def test_error_omits_none_data_from_serialization(self):
        err1 = Error(code=-1, message="test")
        err2 = Error(code=-1, message="test", data=None)
        assert err1.to_protocol() == err2.to_protocol()

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

    def test_ping_rejects_non_ping_request(self):
        with pytest.raises(ValueError):
            protocol_data = {"method": "not_ping"}
            _ = Ping.from_protocol(protocol_data)

    def test_ping_roundtrips(self):
        protocol_data = {"method": "ping"}
        ping = Ping.from_protocol(protocol_data)
        serialized = ping.to_protocol()
        assert serialized == protocol_data


class TestInitialization:
    """
    All initialization-related types together
    """

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
        print("protocol_data", protocol_data)
        print("result", result)
        reconstructed = InitializeResult.from_protocol(protocol_data)
        print("-" * 100)
        print("reconstructed", reconstructed)
        assert reconstructed == result
        assert reconstructed.protocol_version == "2025-03-26"
        assert reconstructed.capabilities is not None
        assert reconstructed.server_info.name == "test_server"
        assert reconstructed.server_info.version == "1.0"
        assert reconstructed.instructions is None


class TestResources:
    def test_list_resource_request_roundtrip_with_cursor(self):
        protocol_data = {"method": "resources/list", "params": {"cursor": "xyz"}}
        req = ListResourcesRequest.from_protocol(protocol_data)
        assert req.cursor == "xyz"
        assert req.method == "resources/list"
        serialized = req.to_protocol()
        assert serialized == protocol_data

    def test_list_resources_request_rejects_improper_method(self):
        protocol_data = {"method": "dont_list"}
        with pytest.raises(ValueError):
            ListResourcesRequest.from_protocol(protocol_data)

    def test_annotations_serializes_to_empty_dict_with_no_data(self):
        annotations = Annotations()
        protocol_data = annotations.to_protocol()
        assert protocol_data == {}

    def test_annotation_rejects_priorities_out_of_range(self):
        with pytest.raises(ValidationError):
            Annotations(priority=100)

    def test_annotation_serialize_with_data(self):
        annotation = Annotations(audience="user", priority=0.5)
        protocol_data = annotation.to_protocol()
        expeceted = {"audience": ["user"], "priority": 0.5}
        assert protocol_data == expeceted

    def test_resource_serializes_with_annotation(self):
        resource = Resource()


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

    def test_progress_notification_roundtrip(self):
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


class TestJSONRPCSerializing:
    def test_serializes_request_with_params(self):
        req = InitializeRequest(
            clientInfo=Implementation(name="Test client", version="1"),
            capabilities=ClientCapabilities(),
        )
        jsonrpc_req = JSONRPCRequest.from_request(req, id=1)
        wire_data = jsonrpc_req.to_wire()
        expected_data = {
            "jsonrpc": JSONRPC_VERSION,
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "clientInfo": {"name": "Test client", "version": "1"},
                "capabilities": {},
            },
        }
        assert wire_data == expected_data

    def test_serializes_with_cursor_for_pagination(self):
        req = ListResourcesRequest(cursor="xyz")
        jsonrpc_req = JSONRPCRequest.from_request(req, id=1)
        wire_data = jsonrpc_req.to_wire()
        expected_data = {
            "jsonrpc": JSONRPC_VERSION,
            "id": 1,
            "method": "resources/list",
            "params": {"cursor": "xyz"},
        }
        assert wire_data == expected_data

    def test_serializes_notification_with_params(self):
        notif = ProgressNotification(
            progressToken="token", progress=1, total=2, message="Halfway home!"
        )
        jsonrpc_notif = JSONRPCNotification.from_notification(notif)
        wire_data = jsonrpc_notif.to_wire()
        expected_data = {
            "jsonrpc": JSONRPC_VERSION,
            "method": "notifications/progress",
            "params": {
                "progressToken": "token",
                "progress": 1,
                "total": 2,
                "message": "Halfway home!",
            },
        }
        assert wire_data == expected_data

    def test_serializes_response_with_params(self):
        result = InitializeResult(
            capabilities=ServerCapabilities(completions={}),
            server_info=Implementation(name="test server", version="1"),
            instructions="Use me well",
        )
        jsonrpc_response = JSONRPCResponse.from_result(result=result, id=1)
        wire_data = jsonrpc_response.to_wire()
        expected_data = {
            "jsonrpc": JSONRPC_VERSION,
            "id": 1,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"completions": {}},
                "serverInfo": {"name": "test server", "version": "1"},
                "instructions": "Use me well",
            },
        }
        assert wire_data == expected_data

    def test_serializes_error_with_error_data(self):
        err = Error(message="Bad. No good.", code=57, data="Specifics")
        jsonrpc_error = JSONRPCError.from_error(error=err, id=1)
        wire_data = jsonrpc_error.to_wire()
        expected_data = {
            "jsonrpc": JSONRPC_VERSION,
            "id": 1,
            "error": {"message": "Bad. No good.", "code": 57, "data": "Specifics"},
        }
        assert wire_data == expected_data

    def test_serializes_request_without_params(self):
        ping = Ping()
        jsonrpc_req = JSONRPCRequest.from_request(ping, id=2)
        wire_data = jsonrpc_req.to_wire()
        expected_data = {"jsonrpc": JSONRPC_VERSION, "id": 2, "method": "ping"}
        assert "params" not in wire_data
        assert wire_data["method"] == "ping"
        assert wire_data == expected_data

    def test_jsonrpc_request_is_outgoing_only(self):
        """JSONRPCRequest is designed for outgoing messages only.

        Incoming wire data should be parsed directly to typed requests,
        not through JSONRPCRequest objects.
        """
        wire_data = {
            "jsonrpc": JSONRPC_VERSION,
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "clientInfo": {"name": "Test client", "version": "1"},
                "capabilities": {},
            },
        }

        # This should fail - we don't support deserializing from wire format
        with pytest.raises((ValidationError, KeyError)):
            JSONRPCRequest.model_validate(wire_data)

        # Instead, parse directly to typed request
        request = InitializeRequest.from_protocol(wire_data)
        assert request.method == "initialize"
        assert request.client_info.name == "Test client"
