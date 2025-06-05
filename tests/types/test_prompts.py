from src.mcp.new_types import ListPromptsRequest, ListPromptsResult, Prompt


class TestPrompts:
    def test_list_prompts_request_method_matches_spec(self):
        request = ListPromptsRequest()
        assert request.method == "prompts/list"

    def test_list_prompts_result_roundtrips(self):
        result = ListPromptsResult(
            prompts=[Prompt(name="test", description="Test prompt")],
        )
        protocol_data = result.to_protocol()
        from_protocol = ListPromptsResult.from_protocol(protocol_data)
        assert from_protocol == result

    def test_prompt_list_result_serializes_with_metadata(self):
        result = ListPromptsResult(
            prompts=[Prompt(name="Test")], metadata={"some_meta": "data"}
        )
        expected = {"prompts": [{"name": "Test"}], "_meta": {"some_meta": "data"}}
        serialized = result.to_protocol()
        print("serialized", serialized)
        print("expected", expected)
        assert serialized == expected
