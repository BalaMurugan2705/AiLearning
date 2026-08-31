"""The question pool used to populate eval/traces.jsonl (Week 5 task).

Mirrors a week of real usage against the docs assistant: mostly natural
questions that do NOT name a version (that's how real users actually ask,
and it's exactly the condition under which sdk_version confusion happens),
plus explicit-version controls, out-of-corpus questions, migration questions,
compound questions, and a few aimed at the two contamination sources sitting
in data/documents/ alongside the real SDK docs — the unrelated Omnumi iOS
card-SDK doc and the leftover W3-Task-Set-E.md task file, both of which get
chunked and indexed like any other .md file.

"demo" is the curated set the team already shows at DX review (the golden set
questions written by hand while reading v3 docs) — used only for the bonus
comparison against the RANDOM sample. It must stay separate from "random" so
the two frequencies being compared aren't contaminated by overlap.
"""

# Natural, version-unspecified questions — the realistic failure surface.
AMBIGUOUS = [
    "What's the default retry backoff for Client.send()?",
    "How do I verify a webhook signature?",
    "What's the maximum page size when fetching messages?",
    "How long does an access token last before I need to refresh it?",
    "How do I paginate through all the messages in a channel?",
    "What does close() actually do?",
    "Is it safe to call close() twice?",
    "What's the maximum message size I can send?",
    "How do retries work when a send fails?",
    "What happens if I hit the rate limit?",
    "How do scopes work for API keys?",
    "How do I authenticate a client?",
    "What region should I connect to?",
    "How do I stream messages in real time instead of polling?",
    "What's the format of a channel identifier?",
    "How do I avoid sending the same message twice?",
    "What does the priority parameter do on send()?",
    "How do I handle a request that times out?",
    "What compression options are available for messages?",
    "How do I register a webhook endpoint?",
    "What happens when a webhook delivery fails?",
    "How do I know if my message was deduplicated?",
    "What fields are on the Receipt object returned by send()?",
    "How do I rotate my API key without downtime?",
    "What's the difference between low, normal and urgent priority?",
    "How do cursors work for pagination?",
    "What does drain_timeout_ms control?",
    "How do I disable retries entirely?",
    "What happens to buffered messages if I force-close the client?",
    "How does the SDK detect a dead connection while streaming?",
    "Can I reuse an idempotency key across two different messages?",
    "What's the retry policy when the broker is temporarily down?",
    "How many times will a failed send be retried by default?",
    "What does the client do differently if I don't pass a region?",
    "Is there a limit to how many concurrent streams I can open?",
]

# Explicit version named — should mostly succeed; a control group.
EXPLICIT_VERSION = [
    "What is the default value of retry_backoff_ms for Client.send() in the v3 SDK?",
    "What's the maximum accepted value for dedupe_window_ms on Client.send()?",
    "Which error code means the bearer token is past its expiry in v3?",
    "What error code does an expired pagination cursor raise in v3?",
    "Which changelog version added the idempotency_key parameter to Client.send() in v2?",
    "How do I verify a Relay webhook signature in v3, given the raw request body and secret?",
    "What hashing algorithm does Relay use to sign webhook requests in v3?",
    "How long is a v3 access token valid before it needs to be refreshed?",
    "What argument do I pass to Client.subscribe() in v3 to get messages as they arrive?",
    "How many delivery attempts will Relay make for a v3 webhook before marking it exhausted?",
    "Is it safe to call Client.close() twice in the v3 SDK?",
    "What's the maximum page_size I can request from Client.fetch() in v3?",
    "What is the default retry backoff for Client.send() in the v2 SDK?",
    "In v2, is RELAY_429 retried automatically?",
    "In v2, what happens when you call close() on a client that never sent a message?",
    "What was the message body size limit before it was raised to 64 KiB in v2?",
    "In v3, what's the HTTP status code for AUTH_SCOPE_DENIED?",
    "In v3, what does the retryable flag mean on a RelayError?",
    "In v2, are keys scoped or all-or-nothing?",
    "In v3, how long is the overlap window after rotating a key?",
]

# Not in the corpus at all, or a near-miss where context exists but the fact doesn't.
OUT_OF_CORPUS = [
    "What is the per-minute rate limit on the /v3/messages endpoint?",
    "Which TLS cipher suites does the Relay broker accept?",
    "What does the urgent priority tier cost per message?",
    "What is the maximum number of concurrent connections allowed per API key?",
    "Which cloud provider hosts the eu-west-1 region?",
    "Does Relay have a Go SDK?",
    "What's the SLA uptime guarantee for the Relay broker?",
    "Is there a sandbox/test mode separate from rk_test_ keys?",
    "How much does the admin scope cost to add to a plan?",
    "Which countries is Relay legally available in?",
]

# Migration-guide questions, v2 -> v3.
MIGRATION = [
    "How do I migrate from v2 to v3?",
    "What breaks when I upgrade from v2 to v3?",
    "Do I need to change my webhook verification code after upgrading to v3?",
    "Will my old v2 retry_backoff_ms value still make sense after moving to v3?",
    "What happened to offset pagination in v3?",
    "How long should I budget for migrating a medium-sized service to v3?",
    "Does upgrading to v3 change how my application code authenticates?",
    "What v2 channel identifiers need to change for v3?",
]

# Compound / multi-fact questions likely to stress single-citation grounding.
COMPOUND = [
    "What's the max message size and how many retries does send() do by default?",
    "How do I authenticate and what scope do I need to send messages?",
    "What's the difference between fetch() and subscribe() and when should I use each?",
    "How does backoff scale across retries, and what's the very first delay?",
    "What happens on close() if there are still buffered messages, and can I skip the wait?",
    "How do I dedupe messages and how long is a dedupe key remembered?",
    "What does a webhook signature check, and what happens if the timestamp is stale?",
    "What's the cursor expiry, and what error do I get if I use an old one?",
]

# Cross-domain trap questions: only answerable from the unrelated Omnumi iOS
# card-SDK doc that happens to be sitting in the same documents directory.
CROSS_DOMAIN = [
    "How do I issue a virtual card through the SDK?",
    "How do I connect a crypto wallet to the SDK?",
    "How does the SDK handle card activation errors?",
    "What does the SDK do for consent management?",
    "What are the two integration modes the SDK offers?",
    "How do I block or report a card as lost?",
    "What does the SDK support for Web3 transaction signing?",
]

# Deliberately generic/ambiguous enough that they could pull chunks from
# either product's docs, or from the stray W3 task file.
DOMAIN_AMBIGUOUS = [
    "How do I handle errors from the SDK?",
    "What SDK operations are available for managing a client?",
    "How should I test my integration against a sandbox before going live?",
    "What is the rubric for measuring whether retrieval finds the right answer?",
    "How do I add a metadata filter and show it changes the top result?",
]

DEMO = list(EXPLICIT_VERSION[:12])  # the curated golden-set questions (Q1-Q12)

RANDOM_POOL = (
    AMBIGUOUS
    + EXPLICIT_VERSION
    + OUT_OF_CORPUS
    + MIGRATION
    + COMPOUND
    + CROSS_DOMAIN
    + DOMAIN_AMBIGUOUS
)
