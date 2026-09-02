# Execution history backend conformance

Every test in this directory receives storage factories through the parametrized `backend_case`
fixture. `BACKEND_CASES` in `conftest.py` is the single backend registry. CHI-177 and CHI-178 can run
the exact same test functions by adding one `BackendCase` containing SQLite or PostgreSQL factories
and their deterministic failure-injection factories; test bodies must not be copied or subclassed.

Backend factories return isolated stores. Failure factories must model append failure,
pre-computation projection failure, and post-computation atomic-publication failure. The latter
computes or attempts the full change but exposes no partial projection. All cursor encodings remain
backend-owned, while the shared tests assert global filter-independent affinity and exclusive
ordering semantics.
