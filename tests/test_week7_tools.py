import json

from agent.tools import TOOL_SCHEMAS, call_tool


def test_three_tools_registered_with_no_name_collisions():
    names = [schema["function"]["name"] for schema in TOOL_SCHEMAS]
    assert sorted(names) == ["check_deprecation", "get_openapi_spec", "search_docs"]


def test_api_version_params_are_enums_not_free_strings():
    for schema in TOOL_SCHEMAS:
        props = schema["function"]["parameters"]["properties"]
        if "api_version" in props:
            assert props["api_version"]["enum"] == ["2022-11-28", "2025-06-01"]


def test_check_deprecation_description_does_not_overlap_other_two():
    descriptions = {s["function"]["name"]: s["function"]["description"] for s in TOOL_SCHEMAS}
    # The 3rd tool's description must name the other two tools directly, so
    # the model is steered toward the right one instead of guessing from
    # similar-sounding verbs -- a plain word-overlap check would fail here
    # on ordinary shared English (the, a, to, one, is), so this checks the
    # actual disambiguating content instead.
    assert descriptions["check_deprecation"] != descriptions["search_docs"]
    assert descriptions["check_deprecation"] != descriptions["get_openapi_spec"]
    assert "search_docs" in descriptions["check_deprecation"]
    assert "get_openapi_spec" in descriptions["check_deprecation"]
    assert "check_deprecation" in descriptions["get_openapi_spec"]


def test_get_openapi_spec_returns_versioned_params():
    result = json.loads(call_tool("get_openapi_spec", {"endpoint": "create_issue", "api_version": "2025-06-01"}))
    names = [p["name"] for p in result["params"]]
    assert "assignees" in names


def test_get_openapi_spec_unknown_endpoint_reports_error_not_fabrication():
    result = json.loads(call_tool("get_openapi_spec", {"endpoint": "nope", "api_version": "2025-06-01"}))
    assert "error" in result


def test_check_deprecation_hit():
    result = json.loads(call_tool("check_deprecation", {"endpoint": "create_repository", "api_version": "2025-06-01"}))
    assert result["deprecated"] is True
    assert "visibility" in result["replacement"]


def test_check_deprecation_miss_is_explicit_not_silent():
    result = json.loads(call_tool("check_deprecation", {"endpoint": "create_release", "api_version": "2025-06-01"}))
    assert result["deprecated"] is False


def test_call_tool_unknown_name_returns_error_json():
    result = json.loads(call_tool("delete_everything", {}))
    assert "error" in result
