---
page_id: client
sdk_version: v3
page_type: reference
---

# Client

The `Client` is the entry point to the Relay SDK. A client owns a connection
pool, a retry policy, and a background flush loop. Construct one per process
and share it; constructing a client per request defeats connection reuse and
will exhaust local ports under load.

```python
from relay import Client

client = Client(api_key="rk_live_...", region="eu-west-1")
```

## Client.send()

Dispatches a single message to a channel and returns a `Receipt`. The call is
synchronous by default: it returns once the broker has durably accepted the
message, not once the recipient has read it.

### Parameters

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `message` | `str` | — | yes | Body of the message. Must be valid UTF-8 and at most 256 KiB after encoding. |
| `channel` | `str` | — | yes | Target channel identifier, in the form `org/team/topic`. Case sensitive. |
| `idempotency_key` | `str` | `None` | no | Client-supplied de-duplication key. Reusing a key within the dedupe window returns the original receipt instead of sending again. |
| `retry_backoff_ms` | `int` | `2000` | no | Base delay in milliseconds before the first retry. Subsequent retries multiply this value by the backoff factor. |
| `retry_backoff_factor` | `float` | `2.0` | no | Multiplier applied to the backoff delay after each failed attempt. A value of `1.0` produces constant-delay retries. |
| `retry_max_attempts` | `int` | `4` | no | Total number of delivery attempts, including the first. Set to `1` to disable retries entirely. |
| `timeout_ms` | `int` | `30000` | no | Total wall-clock budget for the call, covering all retry attempts. Exceeding it raises `RelayTimeout`. |
| `priority` | `str` | `"normal"` | no | One of `"low"`, `"normal"`, or `"urgent"`. Urgent messages bypass the standard queue but are billed at a higher rate. |
| `dedupe_window_ms` | `int` | `600000` | no | How long an `idempotency_key` is remembered by the broker. Maximum accepted value is `86400000` (24 hours). |
| `compression` | `str` | `"gzip"` | no | Wire compression for the payload. One of `"gzip"`, `"zstd"`, or `"none"`. |
| `metadata` | `dict` | `{}` | no | Arbitrary string-to-string map attached to the message. Keys prefixed with `relay.` are reserved and rejected. |
| `callback_url` | `str` | `None` | no | HTTPS endpoint notified on final delivery outcome. Must be registered in the console before use. |

### Retry behaviour

Retries use exponential backoff seeded by `retry_backoff_ms` and multiplied by
`retry_backoff_factor` after each failure. With the defaults, the delays before
attempts two, three and four are 2000 ms, 4000 ms and 8000 ms respectively.
Jitter of up to ±10% is applied to each delay to avoid thundering herds.

Retries are attempted only for transient failures — network errors, `RELAY_503`
and `RELAY_429`. A `RELAY_400` or any authentication error fails immediately
regardless of `retry_max_attempts`.

```python
receipt = client.send(
    message="deployment finished",
    channel="acme/platform/deploys",
    retry_backoff_ms=2000,
    retry_backoff_factor=2.0,
    retry_max_attempts=4,
    idempotency_key="deploy-8817",
)
print(receipt.id, receipt.accepted_at)
```

### Returns

A `Receipt` with fields `id` (string), `accepted_at` (RFC 3339 timestamp),
`attempts` (integer) and `deduplicated` (boolean). When `deduplicated` is true
the message was suppressed and the returned receipt refers to the original
send.

## Client.close()

Shuts the client down. `close()` flushes any messages still buffered in the
background loop, waits up to `drain_timeout_ms` for in-flight sends to settle,
and then releases the connection pool. Messages still unsent when the drain
deadline passes are dropped and reported through the return value.

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `drain_timeout_ms` | `int` | `5000` | no | How long to wait for buffered messages to flush before giving up. |
| `force` | `bool` | `False` | no | Skip the drain entirely and tear the pool down immediately. Buffered messages are lost. |

Calling `close()` twice is safe; the second call is a no-op. Using a client
after `close()` raises `RelayClosed`.

```python
dropped = client.close(drain_timeout_ms=5000)
if dropped:
    logger.warning("relay dropped %d buffered messages", dropped)
```
