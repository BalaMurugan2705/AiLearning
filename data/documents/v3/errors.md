---
page_id: errors
sdk_version: v3
page_type: reference
---

# Errors

Every failure surfaces as a subclass of `RelayError` carrying a stable `code`,
a human-readable `message`, and a `retryable` flag. Branch on `code`; the
message text is not part of the contract and changes between releases.

## Error codes

| Code | HTTP | Retryable | Meaning |
|---|---|---|---|
| `RELAY_400` | 400 | no | Malformed request. The payload failed schema validation before reaching the broker. |
| `AUTH_TOKEN_EXPIRED` | 401 | no | The bearer token is past its expiry. The SDK refreshes automatically; seeing this means the refresh loop is not running. |
| `AUTH_SCOPE_DENIED` | 403 | no | The parent key does not hold the scope required for this call. |
| `RELAY_404` | 404 | no | Channel does not exist, or the key's organisation cannot see it. |
| `RELAY_409` | 409 | no | Idempotency key reused with a different payload inside the dedupe window. |
| `RELAY_413` | 413 | no | Message body exceeds 256 KiB after encoding. |
| `RELAY_429` | 429 | yes | Rate limit exceeded. Honour the `Retry-After` header rather than the SDK's own backoff. |
| `RELAY_503` | 503 | yes | Broker temporarily unavailable. Safe to retry with backoff. |
| `RELAY_504` | 504 | yes | Broker accepted the request but did not settle it within the deadline. Retry with the same idempotency key. |

## Handling

```python
from relay.errors import RelayError

try:
    client.send(message=body, channel=ch)
except RelayError as exc:
    if exc.retryable:
        schedule_retry(body, ch)
    else:
        logger.error("relay rejected send: %s", exc.code)
        raise
```

## Timeouts

`RelayTimeout` is raised when the total budget set by `timeout_ms` is exhausted
across all retry attempts. It is not an error code returned by the broker — it
is raised client-side and carries `attempts`, the number of tries made before
the budget ran out.

A timeout does not mean the message was not delivered. If the broker accepted
the message but the acknowledgement was lost, retrying with the same
`idempotency_key` returns the original receipt rather than sending twice.
