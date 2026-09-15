from agent.spec import API_VERSIONS, ENDPOINT_NAMES, find_deprecation, get_endpoint_spec


def test_endpoint_names_and_versions_loaded():
    assert "create_issue" in ENDPOINT_NAMES
    assert API_VERSIONS == ["2022-11-28", "2025-06-01"]


def test_get_endpoint_spec_returns_versioned_params():
    spec = get_endpoint_spec("create_issue", "2025-06-01")
    names = [p["name"] for p in spec["params"]]
    assert "assignees" in names
    assert "assignee" not in names
    assert spec["x_source"].startswith("github_combined_reference.pdf")


def test_get_endpoint_spec_unknown_endpoint_returns_none():
    assert get_endpoint_spec("delete_universe", "2025-06-01") is None


def test_get_endpoint_spec_unknown_version_returns_none():
    assert get_endpoint_spec("create_issue", "1999-01-01") is None


def test_find_deprecation_hits():
    entry = find_deprecation("create_issue", "2025-06-01")
    assert entry["replacement"] == "assignees (array of strings)"


def test_find_deprecation_misses_when_endpoint_has_no_entry():
    assert find_deprecation("create_pull_request", "2025-06-01") is None


def test_find_deprecation_misses_for_older_version():
    assert find_deprecation("create_issue", "2022-11-28") is None
