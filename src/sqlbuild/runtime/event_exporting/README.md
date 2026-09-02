# Event exporter runtime

Project exporters receive only validated, immutable `LifecycleEvent` values. The CLI registers the
exporter observer after canonical history and native projections, and diagnostics remain on the
separate diagnostic channel.

Each command owns one bounded event queue and one daemon dispatcher. Exporters run in deterministic
declaration order. An invocation runs on a daemon isolation thread so an exporter blocked in
destination code cannot keep the command's non-daemon teardown alive. The dispatcher waits at most
the invocation timeout; after a timeout that exporter is not invoked again and its later attempts
are dropped. This bounds concurrently hung threads to the number of exporters, but Python cannot
terminate those daemon threads or undo destination side effects if they eventually return.

Shutdown stops acceptance, drains only until the shared deadline, accounts queued and unattempted
deliveries as dropped, terminates the event dispatcher, and returns without waiting for timed-out
invocation threads. Concurrent shutdown callers receive the same cached final accounting snapshot.
The shared provider session is retained while any invocation remains live. Teardown runs exactly
once after the last invocation returns; a forever-hung daemon therefore retains its providers until
process exit. A provider is never torn down while live exporter code can still access it. Runtime
failures and the aggregate summary use sanitized diagnostic logging and never publish lifecycle
events.
Failure and summary callbacks run on one bounded daemon notification worker, never on the event
dispatcher or command thread. Notification enqueue is nonblocking and may drop callbacks when its
queue is full. Delivery accounting remains authoritative, and shutdown returns the cached final
summary without waiting for notification callbacks.

Startup first imports public Python modules under `event_exporters/` and collects decorated
declarations without discovering providers. If those modules contain only helpers, SQLBuild does
not import project providers or construct exporter queue, dispatcher, or notification threads.
Normal command-owned project discovery remains responsible for providers needed by nodes and hooks.
