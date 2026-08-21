---
page_id: changelog
sdk_version: v2
page_type: changelog
---

# Changelog

## 2.7.0

Added `idempotency_key` to `Client.send()`. Reusing a key within 60 seconds
returns the original receipt instead of sending again.

Raised the maximum message body from 32 KiB to 64 KiB.

## 2.6.1

Fixed a bug where `close()` could raise if called on a client that had never
sent a message.

## 2.6.0

Added `timeout_ms` to `Client.send()`, defaulting to 10000. Previously the call
had no client-side deadline and could block indefinitely on a hung connection.

## 2.5.0

Retries became configurable through `retry_backoff_ms` and
`retry_max_attempts`. Before this release the retry policy was fixed at three
attempts 500 ms apart and could not be changed.

## 2.4.0

Added `RELAY_429` for rate limiting. It is reported but not retried
automatically; callers must handle it.
