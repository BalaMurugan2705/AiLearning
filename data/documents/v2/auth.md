---
page_id: auth
sdk_version: v2
page_type: reference
---

# Authentication

Relay v2 authenticates with the API key sent directly on every request. There
is no token exchange and no refresh loop.

## API keys

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `api_key` | `str` | — | yes | Long-lived key beginning `rk_live_` or `rk_test_`. Sent as a bearer credential on each call. |
| `region` | `str` | `"us-east-1"` | no | Region whose endpoint is used. |

```python
from relay import Client

client = Client(api_key=os.environ["RELAY_API_KEY"])
```

Because the key travels on every request, v2 has no concept of token expiry.
There is no `AUTH_TOKEN_EXPIRED` condition in v2 and no `refresh_margin`
setting.

## Scopes

v2 keys are all-or-nothing: a key that can read can also send and administer.
Scoped keys were introduced in v3.
