---
page_id: pagination
sdk_version: v3
page_type: reference
---

# Pagination

List endpoints return cursor-paginated results. Cursors are opaque strings
encoding a position in a stable sort order; do not parse or construct them.
Offset pagination was removed in v3.

## Client.fetch()

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `channel` | `str` | — | yes | Channel to read from. |
| `page_size` | `int` | `50` | no | Messages per page. The maximum accepted value is `250`; larger values are rejected with `RELAY_400` rather than silently clamped. |
| `cursor` | `str` | `None` | no | Position returned by a previous call as `next_cursor`. Omit for the first page. |
| `direction` | `str` | `"forward"` | no | `"forward"` reads oldest to newest; `"backward"` reads newest to oldest. |

A page response carries `items`, `next_cursor` and `has_more`. When `has_more`
is `False`, `next_cursor` is `None` and iteration is complete.

```python
cursor, out = None, []
while True:
    page = client.fetch(channel=ch, page_size=250, cursor=cursor)
    out.extend(page.items)
    if not page.has_more:
        break
    cursor = page.next_cursor
```

## Cursor stability

A cursor remains valid for 7 days. Using an expired cursor raises `RELAY_410`
and requires restarting from the first page. Cursors are scoped to the channel
and direction that produced them; reusing a forward cursor on a backward read
raises `RELAY_400`.

Messages deleted between pages are skipped rather than leaving gaps, so a
consumer walking pages sees a consistent sequence even under concurrent
deletion.
