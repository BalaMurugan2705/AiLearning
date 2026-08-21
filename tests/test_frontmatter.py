import pytest

from rag.frontmatter import FrontMatterError, parse_front_matter

VALID = """---
page_id: client
sdk_version: v3
page_type: reference
---

# Client

Body text.
"""


def test_parses_required_fields():
    meta, _ = parse_front_matter(VALID)
    assert meta == {"page_id": "client", "sdk_version": "v3", "page_type": "reference"}


def test_strips_front_matter_from_body():
    _, body = parse_front_matter(VALID)
    assert body.lstrip().startswith("# Client")
    assert "page_id" not in body


def test_raises_when_front_matter_missing():
    with pytest.raises(FrontMatterError, match="no front matter"):
        parse_front_matter("# Client\n\nBody text.\n")


def test_raises_when_required_field_missing():
    text = "---\npage_id: client\nsdk_version: v3\n---\n\n# Client\n"
    with pytest.raises(FrontMatterError, match="page_type"):
        parse_front_matter(text)


def test_raises_when_required_field_empty():
    text = "---\npage_id: client\nsdk_version:\npage_type: reference\n---\n\n# Client\n"
    with pytest.raises(FrontMatterError, match="sdk_version"):
        parse_front_matter(text)


def test_raises_on_unknown_page_type():
    text = "---\npage_id: c\nsdk_version: v3\npage_type: tutorial\n---\n\n# C\n"
    with pytest.raises(FrontMatterError, match="page_type"):
        parse_front_matter(text)


def test_does_not_coerce_no_to_boolean():
    """YAML 1.1 resolves a bare `no` to False. We keep values as strings so a
    field like `required: no` survives as the text the author wrote."""
    text = "---\npage_id: c\nsdk_version: v3\npage_type: reference\nrequired: no\n---\n\n# C\n"
    meta, _ = parse_front_matter(text)
    assert meta["required"] == "no"


def test_rejects_line_that_is_not_key_value():
    text = "---\npage_id: client\n- a list item\n---\n\n# C\n"
    with pytest.raises(FrontMatterError, match="could not parse"):
        parse_front_matter(text)
