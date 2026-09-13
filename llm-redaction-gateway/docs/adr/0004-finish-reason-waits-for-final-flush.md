# finish_reason: "stop" waits for the final flush, it doesn't ride the upstream's last chunk

The upstream's final chunk can carry `finish_reason: "stop"` while the
Holdback Buffer still has unflushed text in it. Relaying that chunk
unmodified would tell the client the response is complete one step too
early — a client that treats `"stop"` as "stop listening" will silently
drop anything sent afterward, so the buffer's final flush (already
required on stream end) would never actually reach the client even
though it was correctly redacted.

`finish_reason: "stop"` is therefore held back the same way buffered text
is (see ADR-0001) and only attached to whichever chunk the gateway
actually emits last, after its own final flush — never relayed on the
chunk it originally arrived on.
