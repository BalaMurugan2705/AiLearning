---
page_id: client
sdk_version: v2
page_type: reference
---

# Client

The `Client` is the entry point to the Relay SDK. Construct one per process and
share it across threads.

```python
from relay import Client

client = Client(api_key="rk_live_...", region="us-east-1")
```

## Client.send()

Dispatches a single message to a channel and returns a `Receipt`.

### Parameters

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `message` | `str` | — | yes | Body of the message. Must be valid UTF-8 and at most 64 KiB. |
| `channel` | `str` | — | yes | Target channel identifier, in the form `org/topic`. |
| `idempotency_key` | `str` | `None` | no | Client-supplied de-duplication key. |
| `retry_backoff_ms` | `int` | `500` | no | Base delay in milliseconds before the first retry. |
| `retry_max_attempts` | `int` | `3` | no | Total number of delivery attempts, including the first. |
| `timeout_ms` | `int` | `10000` | no | Total wall-clock budget for the call. |

### Default retry backoff

The default retry backoff for `Client.send()` is 500 ms. Retries use a fixed
delay: every attempt waits the same `retry_backoff_ms` interval, with no
multiplier and no jitter. With the defaults, the delays before attempts two and
three are both 500 ms.

Retries are attempted for network errors and `RELAY_503` only. `RELAY_429` is
not retried automatically in v2.

```python
receipt = client.send(
    message="deployment finished",
    channel="acme/deploys",
    retry_backoff_ms=500,
    retry_max_attempts=3,
)
```

### Returns

A `Receipt` with fields `id` and `accepted_at`.

## Client.close()

Releases the connection pool. v2 has no background flush loop, so `close()`
returns immediately and there is nothing to drain.

```python
client.close()
```
