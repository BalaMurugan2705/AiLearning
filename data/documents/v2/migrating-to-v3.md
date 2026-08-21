---
page_id: migrating-to-v3
sdk_version: v2
page_type: guide
---

# Migrating from v2 to v3

This guide covers the breaking changes between v2 and v3 and the order to make
them in. Budget roughly a day for a service of moderate size.

## Breaking changes

Channel identifiers gained a segment. A v2 channel `org/topic` becomes
`org/team/topic` in v3, and the v3 broker rejects two-segment identifiers with
`RELAY_400` rather than inferring a team.

Authentication changed from long-lived keys on every request to short-lived
bearer tokens minted from a key. Application code is unaffected — the SDK
performs the exchange — but network policy that pinned the v2 auth endpoint
needs updating.

Retry semantics changed from fixed-delay to exponential backoff, and the
default base delay changed. Any service that hand-tuned `retry_backoff_ms`
against v2's fixed-delay behaviour should re-derive the value rather than
carrying it across.

Offset pagination was removed entirely in favour of cursors. Code that computed
page offsets must be rewritten to thread `next_cursor`.

## Order of work

1. Update channel identifiers everywhere, including in stored configuration.
2. Move to the v3 client and let it manage tokens.
3. Re-derive retry settings against the new exponential policy.
4. Replace offset pagination with cursor iteration.
5. Re-register webhook endpoints; v2 signatures are not accepted by v3.

## What did not change

Message bodies are still UTF-8 strings, receipts still carry `id` and
`accepted_at`, and `RELAY_503` still means the same thing. The error type
hierarchy is source-compatible for the codes that exist in both versions.
