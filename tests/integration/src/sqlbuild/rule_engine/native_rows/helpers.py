import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.rule_engine._helpers.run import native_rows as native_rows_module

RULES_FIXTURE: Path = Path("tests/e2e/fixtures/waffle_shop")
RULES_CONFIG: str = '\n[rules]\nselect = ["SQBR"]\n'
EDITED_MODEL: str = "models/staging/stg_orders.sql"

type FindingKey = tuple[str, str, int | None, int | None, str]


def write_rules_fixture(*, project_dir: Path) -> None:
    """Copy the neutral fixture and select every built-in rule."""

    _ = shutil.copytree(RULES_FIXTURE, project_dir)
    config: Path = project_dir / "sqlbuild_project.toml"
    _ = config.write_text(config.read_text(encoding="utf-8") + RULES_CONFIG, encoding="utf-8")


def record_built_rows(*, monkeypatch: pytest.MonkeyPatch, engine: str) -> Counter[str]:
    """Count the rules request rows the native builder reports it built."""

    built: Counter[str] = Counter()
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine)

    def counted(*, stage: NativeStage, kind: str, units: int = 1) -> None:
        built[f"{stage.value}:{kind}"] += units

    monkeypatch.setattr(native_rows_module, "report_native_answer", counted)
    return built


def built_rows(built: Counter[str]) -> tuple[int, int, int]:
    """Models, SQL tests and scenarios built natively, in that order."""

    return (
        built["rules_request:models"],
        built["rules_request:sql_tests"],
        built["rules_request:sql_scenarios"],
    )


def compile_rules(
    *, project_dir: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[tuple[FindingKey, ...], tuple[int, int]]:
    """Compile with the rules cache on; return findings in order and rule cache hits and misses."""

    _ = main(["--project-dir", str(project_dir), "compile", "--json"])
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, Any]] = cast(list[dict[str, Any]], payload["diagnostics"])
    timings: dict[str, int] = cast(dict[str, int], payload["compile_timings"])
    return (
        tuple(
            (item["code"], item["path"], item.get("line"), item.get("column"), item["message"])
            for item in diagnostics
        ),
        (timings["rule_cache_hits"], timings["rule_cache_misses"]),
    )


def struct_passthrough_files(*, declared_type: str) -> dict[str, str]:
    """An enforced passthrough of a STRUCT column whose contract declares `declared_type`."""

    return {
        "sqlbuild_project.toml": (
            'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRCONTRACT105"]\n\n'
            '[defaults]\ncontract = "enforced"\n'
        ),
        "models/stg_orders.sql": (
            "MODEL (description 'Staged orders.',\n"
            "  columns (order_id (type INTEGER), detail (type 'STRUCT(\"café\" INTEGER)')),\n"
            ");\n\n"
            "SELECT CAST(1 AS INTEGER) AS order_id,\n"
            "  CAST({'café': 1} AS STRUCT(\"café\" INTEGER)) AS detail\n"
        ),
        "models/orders.sql": (
            "MODEL (description 'Typed orders.',\n"
            f"  columns (order_id (type INTEGER), detail (type '{declared_type}')),\n"
            ");\n\n"
            'SELECT order_id, detail\nFROM __ref("stg_orders")\n'
        ),
    }


def compile_codes(
    *, project_dir: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, tuple[str, ...]]:
    """Compile to JSON; return the exit code and every diagnostic code in order."""

    exit_code: int = main(["--project-dir", str(project_dir), "compile", "--json"])
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, Any]] = cast(list[dict[str, Any]], payload["diagnostics"])
    return exit_code, tuple(item["code"] for item in diagnostics)


def edit_model(*, project_dir: Path) -> None:
    """Change one model's SQL so only its rules facts change."""

    model: Path = project_dir / EDITED_MODEL
    _ = model.write_text(model.read_text(encoding="utf-8") + "\n-- reviewed\n", encoding="utf-8")


TYPE_PROOF_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRCONTRACT105"]\n\n'
        '[defaults]\ncontract = "enforced"\n'
    ),
    "models/stg_orders.sql": (
        "MODEL (description 'Staged orders.',\n"
        "  columns (order_id (type INTEGER), amount (type INTEGER)),\n"
        ");\n\n"
        "SELECT CAST(1 AS INTEGER) AS order_id, CAST(5 AS INTEGER) AS amount\n"
    ),
    "models/orders.sql": (
        "MODEL (description 'Typed orders.',\n"
        "  columns (order_id (type INTEGER), amount (type BIGINT)),\n"
        ");\n\n"
        'SELECT order_id, amount\nFROM __ref("stg_orders")\n'
    ),
}


def write_files(*, project_dir: Path, files: dict[str, str]) -> None:
    """Write project files at their project-relative paths."""

    for relative, contents in files.items():
        path: Path = project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
