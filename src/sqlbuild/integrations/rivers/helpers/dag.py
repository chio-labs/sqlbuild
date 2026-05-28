"""SQLBuild DAG artifact loading helpers for Rivers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlbuild.integrations.rivers.exceptions import RiversDagInputError
from sqlbuild.integrations.rivers.types import SqlBuildDagInput


def load_sqlbuild_dag(dag: SqlBuildDagInput) -> Mapping[str, Any]:
    """Load a SQLBuild DAG artifact from a mapping or JSON file path."""

    if not isinstance(dag, (str, Path)):
        payload: Mapping[str, Any] = dag
    else:
        path: Path = Path(dag)
        try:
            loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise RiversDagInputError(f"could not read SQLBuild DAG artifact: {path}") from error
        except json.JSONDecodeError as error:
            raise RiversDagInputError(
                f"SQLBuild DAG artifact is not valid JSON: {path}: {error.msg}"
            ) from error
        if not isinstance(loaded, Mapping):
            raise RiversDagInputError("SQLBuild DAG artifact must be a JSON object")
        payload = loaded

    _validate_dag_payload(payload)
    return payload


def _validate_dag_payload(payload: Mapping[str, Any]) -> None:
    version: object = payload.get("version")
    if version != 1:
        raise RiversDagInputError(f"unsupported SQLBuild DAG artifact version: {version!r}")
    for key in ("nodes", "edges", "checks"):
        value: object = payload.get(key)
        if not isinstance(value, list):
            raise RiversDagInputError(f"SQLBuild DAG artifact field '{key}' must be a list")
