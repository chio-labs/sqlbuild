"""PoC only: run `sqb compile` in-process and record every native analysis call to JSONL.

Usage: python capture_native.py OUT_DIR -- <sqb arguments>

The native `ProjectCatalog` is wrapped by a recording proxy. Each line of OUT_DIR/ops.jsonl is
one call in the order the compiler made it, with its inputs, outputs and wall time. Mappings are
stored as lists of pairs so key order survives JSON round trips.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path

import orjson

OUT_DIR = Path(sys.argv[1])
SQB_ARGS = sys.argv[sys.argv.index("--") + 1 :]
OUT_DIR.mkdir(parents=True, exist_ok=True)
_LOG = (OUT_DIR / "ops.jsonl").open("wb")
_LOCK = threading.Lock()
_SEQ = itertools.count()
_IDS = itertools.count()
_LOCAL = threading.local()
_T0 = time.perf_counter()


def _pairs(value: object) -> object:
    if isinstance(value, Mapping):
        return [[str(key), _pairs(item)] for key, item in value.items()]
    if isinstance(value, tuple | list):
        return [_pairs(item) for item in value]
    if isinstance(value, Exception):
        return {"error": f"{type(value).__name__}: {value}"}
    if hasattr(value, "value") and hasattr(value, "name"):
        return value.value
    return value


def _emit(record: dict[str, object]) -> None:
    record["context"] = getattr(_LOCAL, "names", None)
    record["thread"] = threading.current_thread().name
    with _LOCK:
        record["seq"] = next(_SEQ)
        _LOG.write(orjson.dumps(record, default=repr) + b"\n")


def _timed(call):
    start = time.perf_counter()
    result = call()
    return result, (time.perf_counter() - start), start - _T0


import sqlbuild._native as _native  # noqa: E402

_NativeCatalog = _native.ProjectCatalog
_native_normalize = _native.normalize_analysis_sqls
_native_compact = _native.analyze_project_queries_compact_json


class RecordingJob:
    def __init__(self, job: object, job_id: int) -> None:
        self._job = job
        self._id = job_id

    def run(self) -> bytes:
        result, seconds, at = _timed(self._job.run)
        _emit({"op": "run", "job": self._id, "seconds": seconds, "at": at,
               "result": result.decode()})
        return result


class RecordingCatalog:
    def __init__(self, request: object = None, *, _wrap: object = None, _parent: int = -1,
                 _relations: object = None) -> None:
        self._id = next(_IDS)
        if _wrap is not None:
            self._native = _wrap
            _emit({"op": "with_relations", "id": self._id, "parent": _parent,
                   "relations": _pairs(_relations)})
            return
        self._native, seconds, at = _timed(lambda: _NativeCatalog(request))
        _emit({"op": "new", "id": self._id, "seconds": seconds, "at": at,
               "request": _pairs(request)})

    def with_relations(self, relations):
        native = self._native.with_relations(relations)
        return RecordingCatalog(_wrap=native, _parent=self._id, _relations=relations)

    def update_relations(self, relations):
        result, seconds, at = _timed(lambda: self._native.update_relations(relations))
        _emit({"op": "update_relations", "id": self._id, "seconds": seconds, "at": at,
               "relations": _pairs(relations)})
        return result

    def update_analysis(self, relations):
        result, seconds, at = _timed(lambda: self._native.update_analysis(relations))
        _emit({"op": "update_analysis", "id": self._id, "seconds": seconds, "at": at,
               "relations": _pairs(relations)})
        return result

    def register_override(self, relations):
        result, seconds, at = _timed(lambda: self._native.register_override(relations))
        _emit({"op": "register_override", "id": self._id, "seconds": seconds, "at": at,
               "relations": _pairs(relations), "result": result})
        return result

    def prepare_compact(self, payload):
        job, seconds, at = _timed(lambda: self._native.prepare_compact(payload))
        job_id = next(_IDS)
        _emit({"op": "prepare_compact", "id": self._id, "job": job_id, "seconds": seconds,
               "at": at, "payload": bytes(payload).decode(),
               "query_sqls": getattr(_LOCAL, "query_sqls", None)})
        return RecordingJob(job, job_id)

    def binding_results(self, requests):
        result, seconds, at = _timed(lambda: self._native.binding_results(requests))
        _emit({"op": "binding_results", "id": self._id, "seconds": seconds, "at": at,
               "requests": _pairs(requests), "result": _pairs(result)})
        return result

    def normalize_analysis_sqls(self, *, dialect, requests):
        result, seconds, at = _timed(
            lambda: self._native.normalize_analysis_sqls(dialect=dialect, requests=requests))
        _emit({"op": "normalize", "id": self._id, "seconds": seconds, "at": at,
               "dialect": dialect, "requests": _pairs(requests), "result": _pairs(result)})
        return result

    def inferred_schema(self, *, sql, columns, inputs):
        result, seconds, at = _timed(
            lambda: self._native.inferred_schema(sql=sql, columns=columns, inputs=inputs))
        _emit({"op": "inferred_schema", "id": self._id, "seconds": seconds, "at": at})
        return result

    def validation_payload(self, requests):
        result, seconds, at = _timed(lambda: self._native.validation_payload(requests))
        _emit({"op": "validation_payload", "id": self._id, "seconds": seconds, "at": at})
        return result


def _module_normalize(*, dialect, requests):
    result, seconds, at = _timed(lambda: _native_normalize(dialect=dialect, requests=requests))
    _emit({"op": "normalize", "id": None, "seconds": seconds, "at": at, "dialect": dialect,
           "requests": _pairs(requests), "result": _pairs(result)})
    return result


def _module_compact(request_json):
    result, seconds, at = _timed(lambda: _native_compact(request_json))
    _emit({"op": "compact_json", "seconds": seconds, "at": at, "payload": request_json,
           "result": result})
    return result


_native.ProjectCatalog = RecordingCatalog
_native.normalize_analysis_sqls = _module_normalize
_native.analyze_project_queries_compact_json = _module_compact

from sqlbuild.compiler.compile.classes import binding_dataflow as _dataflow  # noqa: E402

_init = _dataflow.BindingDataflow.__init__
_analyze_ready = _dataflow.BindingDataflow._analyze_ready


def _recording_init(self, **kwargs):
    _init(self, **kwargs)
    _emit({"op": "dataflow", "names": list(kwargs["names"]),
           "dependencies": [[name, list(deps)] for name, deps in self._dependencies.items()]})


def _recording_analyze_ready(self, ready):
    previous = getattr(_LOCAL, "names", None)
    _LOCAL.names = list(ready)
    _emit({"op": "ready", "query_sqls": [
        [name, _digest(self._by_name[name].query_sql)] for name in ready]})
    try:
        return _analyze_ready(self, ready)
    finally:
        _LOCAL.names = previous


def _digest(text):
    return hashlib.blake2b(text.encode(), digest_size=12).hexdigest()


from sqlbuild.compiler.compile._helpers.analysis import compact as _compact  # noqa: E402

_prepare_batch = _compact._prepare_compact_analysis_batch


def _recording_prepare_batch(*, inputs, **kwargs):
    # Kept after return: the native prepare call follows on the same thread.
    _LOCAL.query_sqls = [_digest(sql) for sql in inputs.query_sqls]
    return _prepare_batch(inputs=inputs, **kwargs)


_compact._prepare_compact_analysis_batch = _recording_prepare_batch
_dataflow.BindingDataflow.__init__ = _recording_init
_dataflow.BindingDataflow._analyze_ready = _recording_analyze_ready

from sqlbuild.cli.entry.main.entry import main  # noqa: E402

sys.argv = ["sqb", *SQB_ARGS]
try:
    main()
except SystemExit as exit_:
    code = exit_.code
else:
    code = 0
_LOG.close()
os._exit(code if isinstance(code, int) else 1)
