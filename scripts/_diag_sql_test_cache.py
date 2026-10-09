"""Throwaway CI diagnostic: report why a warm SQL-test artifact cache lookup missed."""

import json
import sys
from pathlib import Path

import sqlbuild.cli.commands._helpers.compile.sql_test_artifact_cache as cache
import sqlbuild.cli.commands._helpers.compile.target_writer as tw

_STATE = Path("target") / "diag-identities.json"
_previous = json.loads(_STATE.read_text()) if _STATE.is_file() else {}
_current = {}
_orig_identity = tw.sql_test_artifact_identity
_orig_match = tw.artifact_matches_cache_record


def _identity(**kw):
    test = kw["test"]
    context = kw["context"]
    _current[test.name] = {
        "common": context.common_identity,
        "test": cache._payload_digest(cache._test_payload(test=test)),
        "chain": [[n, context.model_identities.get(n)] for n in kw["model_chain_names"]],
    }
    return _orig_identity(**kw)


def _match(**kw):
    found = _orig_match(**kw)
    if found is None:
        record = kw["record"]
        path = kw["tests_root"] / record.relative_path
        stat = path.stat() if path.exists() else None
        name = next((n for n in _current if n in str(record.relative_path)), None)
        changed = {
            key: [_previous.get(name, {}).get(key), _current.get(name, {}).get(key)]
            for key in ("common", "test", "chain")
            if _previous.get(name, {}).get(key) != _current.get(name, {}).get(key)
        }
        print(
            "DIAG miss "
            + json.dumps(
                {
                    "rel": str(record.relative_path),
                    "id_eq": record.identity == kw["identity"],
                    "size": [record.size, stat and stat.st_size],
                    "mtime": [record.mtime_ns, stat and stat.st_mtime_ns],
                    "changed": changed,
                }
            ),
            file=sys.stderr,
        )
    return found


tw.sql_test_artifact_identity = _identity
tw.artifact_matches_cache_record = _match
from sqlbuild.cli.entry.main.entry import main  # noqa: E402

try:
    code = main()
finally:
    if _current and Path("target").is_dir():
        _STATE.write_text(json.dumps({**_previous, **_current}))
sys.exit(code)
