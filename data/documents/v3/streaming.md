---
page_id: streaming
sdk_version: v3
page_type: reference
---

# Streaming

Streaming subscribes to a channel and yields messages as they arrive, over a
single long-lived HTTP/2 connection. Use it for tailing a channel; use
`Client.fetch()` for bounded historical reads.

## Client.subscribe()

Opens a stream and returns an iterator. The iterator blocks between messages
and terminates when the server closes the stream or `max_messages` is reached.

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `channel` | `str` | — | yes | Channel to tail, in the form `org/team/topic`. |
| `stream` | `bool` | `False` | no | Must be `True` to receive incremental messages. When `False` the call buffers the whole response and returns a list. |
| `from_cursor` | `str` | `None` | no | Resume position. When omitted the stream starts at the newest message and does not replay history. |
| `heartbeat_ms` | `int` | `15000` | no | Interval at which the server emits keepalive frames. Set to `0` to disable, at the cost of slower dead-connection detection. |
| `max_messages` | `int` | `None` | no | Stop after this many messages. `None` streams until the connection closes. |

Enable streaming by passing `stream=True`; the default is `False`, which
buffers and returns a plain list instead of an iterator.

```python
for message in client.subscribe(
    channel="acme/platform/deploys",
    stream=True,
    heartbeat_ms=15000,
):
    print(message.id, message.body)
```

## Reconnection

The SDK reconnects automatically when the connection drops, resuming from the
cursor of the last message it yielded. Reconnection uses the same exponential
backoff policy as `Client.send()`, capped at 60 seconds between attempts.

Messages are delivered at least once. A reconnect can replay the most recent
message if it was yielded but its cursor had not yet been acknowledged, so
consumers must tolerate duplicates.

```python
cursor = None
for message in client.subscribe(channel=ch, stream=True, from_cursor=cursor):
    process(message)
    cursor = message.cursor
```

## Backpressure

If a consumer reads slower than the channel produces, the server buffers up to
2000 messages per subscription and then begins dropping the oldest. Dropped
messages are reported as a `StreamLagged` event carrying the number of messages
lost, which is delivered inline in the iterator.
