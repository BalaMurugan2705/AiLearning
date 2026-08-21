---
page_id: errors
sdk_version: v2
page_type: reference
---

# Errors

Failures surface as `RelayError` carrying a `code` and a `message`.

## Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `RELAY_400` | 400 | Malformed request. |
| `RELAY_401` | 401 | API key missing, malformed, or revoked. |
| `RELAY_404` | 404 | Channel does not exist. |
| `RELAY_429` | 429 | Rate limit exceeded. Not retried automatically in v2. |
| `RELAY_503` | 503 | Broker temporarily unavailable. Safe to retry. |

v2 has no `retryable` flag on errors. Callers must decide from the code which
failures are worth retrying.

```python
from relay.errors import RelayError

try:
    client.send(message=body, channel=ch)
except RelayError as exc:
    if exc.code in ("RELAY_503",):
        schedule_retry(body, ch)
    else:
        raise
```
