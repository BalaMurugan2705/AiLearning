---
page_id: auth
sdk_version: v3
page_type: reference
---

# Authentication

Relay authenticates with short-lived bearer tokens minted from a long-lived API
key. The SDK handles the exchange transparently; you supply the key and the
client refreshes tokens in the background.

## Token lifecycle

An access token issued by `POST /v3/auth/token` is valid for 3600 seconds. The
SDK refreshes it when 80% of its lifetime has elapsed, so a healthy client
refreshes roughly every 48 minutes. Refresh happens on a background thread and
does not block calls in flight.

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `api_key` | `str` | — | yes | Long-lived key beginning `rk_live_` or `rk_test_`. Never ship a live key to a client device. |
| `region` | `str` | `"us-east-1"` | no | Region whose token endpoint is used. Tokens are not portable between regions. |
| `refresh_margin` | `float` | `0.8` | no | Fraction of token lifetime after which a refresh is attempted. Values above `0.95` are rejected. |
| `token_cache` | `TokenCache` | `MemoryCache()` | no | Where minted tokens are stored. Supply a shared cache to avoid one refresh per process. |

```python
from relay import Client
from relay.auth import RedisTokenCache

client = Client(
    api_key=os.environ["RELAY_API_KEY"],
    region="eu-west-1",
    token_cache=RedisTokenCache(url=os.environ["REDIS_URL"]),
)
```

## Scopes

Keys carry scopes that bound what the minted token may do. A token can never
hold a scope its parent key lacks.

| Scope | Grants |
|---|---|
| `send` | Dispatch messages to any channel the key's organisation owns. |
| `read` | Read receipts, delivery status and channel metadata. |
| `admin` | Rotate keys, register webhook endpoints, and change billing tier. |

Requesting a scope the key does not hold fails with `AUTH_SCOPE_DENIED` at mint
time, not at call time. Check scopes during deployment rather than discovering
them in production traffic.

## Rotation

Keys are rotated from the console or with `Client.rotate_key()`. Rotation mints
a replacement and marks the old key for expiry after a 24 hour overlap window,
during which both keys authenticate. Tokens already minted from the old key
remain valid until their own expiry.
