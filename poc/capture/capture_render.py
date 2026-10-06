"""PoC only: run `sqb compile` in-process and dump each rendered model input to JSON.

Usage: python capture_render.py OUT_JSON -- <sqb arguments>

Records, per model: rendered query SQL, references, macro dependencies and the effective config
values, plus the wall time of the Python per-model rendering loop and of each user macro call.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import orjson

OUT = Path(sys.argv[1])
SQB_ARGS = sys.argv[sys.argv.index("--") + 1 :]
_STATS: dict[str, float] = {"build_model_inputs_s": 0.0, "macro_calls": 0, "macro_s": 0.0}
_MODELS: list[dict[str, object]] = []

from sqlbuild.compiler.compile.main import _build_compile_inputs as _bci  # noqa: E402

_build = _bci.build_model_inputs


def _plain(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return repr(value)


def _recording_build(**kwargs):
    start = time.perf_counter()
    result = _build(**kwargs)
    _STATS["build_model_inputs_s"] += time.perf_counter() - start
    for model in result:
        _MODELS.append(
            {
                "name": model.model_file.file_path.stem,
                "path": str(model.model_file.relative_path),
                "query_sql": model.query_sql,
                "references": [
                    [str(getattr(ref.ref_kind, "value", ref.ref_kind)), ref.ref_name,
                     ref.ref_package]
                    for ref in model.references
                ],
                "macro_deps": list(model.macro_deps),
                "config": _plain(model.config.values),
            }
        )
    return result


_bci.build_model_inputs = _recording_build

from sqlbuild.compiler.compile._helpers.render import macros as _expansion  # noqa: E402

if hasattr(_expansion, "_call_loaded_macro"):
    _call = _expansion._call_loaded_macro

    def _recording_call(*args, **kwargs):
        start = time.perf_counter()
        try:
            return _call(*args, **kwargs)
        finally:
            _STATS["macro_calls"] += 1
            _STATS["macro_s"] += time.perf_counter() - start

    _expansion._call_loaded_macro = _recording_call

from sqlbuild.cli.entry.main.entry import main  # noqa: E402

sys.argv = ["sqb", *SQB_ARGS]
try:
    main()
except SystemExit as exit_:
    code = exit_.code
else:
    code = 0
OUT.write_bytes(orjson.dumps({"stats": _STATS, "models": _MODELS}, default=repr))
os._exit(code if isinstance(code, int) else 1)
