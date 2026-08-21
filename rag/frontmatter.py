"""Strict front matter parsing for ingested documents.

Deliberately not YAML. The corpus is documentation about parameter tables
whose `Required` column contains values like `no`, and YAML 1.1 resolves a
bare `no` to boolean False. A parser that only understands `key: value`
string pairs cannot silently coerce anything, and rejects what it does not
recognise instead of guessing.
"""

REQUIRED_FIELDS = ("page_id", "sdk_version", "page_type")
ALLOWED_PAGE_TYPES = ("reference", "guide", "changelog")

_DELIMITER = "---"


class FrontMatterError(ValueError):
    """Raised when front matter is absent, malformed, or incomplete."""


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Return (metadata, body) for a document beginning with `---` front matter.

    Raises FrontMatterError rather than returning partial metadata: a chunk
    indexed with a missing or wrong sdk_version corrupts every downstream
    measurement invisibly, so a loud failure at ingest is the cheaper outcome.
    """
    stripped = text.lstrip()
    if not stripped.startswith(_DELIMITER):
        raise FrontMatterError("document has no front matter block")

    after_open = stripped[len(_DELIMITER) :].lstrip("\r\n")
    end = after_open.find(f"\n{_DELIMITER}")
    if end == -1:
        raise FrontMatterError("front matter block is not closed")

    block = after_open[:end]
    body = after_open[end + len(_DELIMITER) + 1 :]

    meta: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip() or " " in key.strip():
            raise FrontMatterError(f"could not parse front matter line: {line!r}")
        meta[key.strip()] = value.strip()

    for field in REQUIRED_FIELDS:
        if not meta.get(field):
            raise FrontMatterError(f"front matter is missing required field: {field}")

    if meta["page_type"] not in ALLOWED_PAGE_TYPES:
        raise FrontMatterError(
            f"page_type must be one of {ALLOWED_PAGE_TYPES}, got {meta['page_type']!r}"
        )

    return meta, body
