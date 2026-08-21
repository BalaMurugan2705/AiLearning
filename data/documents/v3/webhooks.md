---
page_id: webhooks
sdk_version: v3
page_type: reference
---

# Webhooks

Relay delivers asynchronous delivery outcomes to the `callback_url` registered
on a send. Every webhook request is signed so that receivers can verify it
originated from Relay and has not been altered in transit.

## Signature verification

Each request carries the signature in the `X-Relay-Signature-V3` header. The
signature is computed as HMAC-SHA256 over the concatenation of the request
timestamp, a literal `.` separator, and the raw request body, keyed by your
endpoint's signing secret.

| Header | Type | Required | Description |
|---|---|---|---|
| `X-Relay-Signature-V3` | `str` | yes | Hex-encoded HMAC-SHA256 digest of `timestamp + "." + body`. |
| `X-Relay-Timestamp` | `str` | yes | Unix epoch seconds at which the request was signed. |
| `X-Relay-Delivery-Id` | `str` | yes | Unique identifier for this delivery attempt, stable across retries of the same event. |

Verification must be done against the **raw** request body. Parsing the JSON
and re-serialising it will change byte ordering and whitespace, and the digest
will not match.

```python
from relay.webhooks import verify

verify(
    body=request.raw_body,
    signature=request.headers["X-Relay-Signature-V3"],
    timestamp=request.headers["X-Relay-Timestamp"],
    secret=WEBHOOK_SECRET,
    tolerance_seconds=300,
)
```

`verify()` raises `SignatureMismatch` when the digest does not match and
`SignatureExpired` when the timestamp is outside `tolerance_seconds`. The
default tolerance is 300 seconds; widening it beyond 900 is rejected.

## Retry schedule

A webhook endpoint that does not return a 2xx status within 10 seconds is
retried. Relay makes at most 6 delivery attempts spread over 24 hours, at
intervals of 30 seconds, 5 minutes, 30 minutes, 2 hours, 6 hours and 18 hours.
After the final attempt the delivery is marked `exhausted` and no further
notification is sent.

Endpoints must be idempotent. `X-Relay-Delivery-Id` is stable across retries of
the same event and is the correct key to deduplicate on.
