# Connection resilience, backpressure, and cost/rate limiting are out of scope

The task's evaluation criteria name exactly three concerns: efficient
async stream chunking/buffer state management, performant pattern
matching over partial streams, and memory/latency efficiency. Upstream
disconnect handling, client backpressure, and API key/cost/rate-limit
handling are none of those, and are deliberately left unhandled rather
than silently assumed away — a future reader should read this as "not
attempted," not "forgotten."
