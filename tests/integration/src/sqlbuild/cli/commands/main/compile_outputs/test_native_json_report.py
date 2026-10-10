"""The native JSON report keeps the orjson report contract and its `json.dumps` fallback."""

import json
import logging
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import orjson
import pytest

import sqlbuild._native as native_module
from sqlbuild.cli.commands._helpers.compile import output as output_module
from tests.integration.src.sqlbuild.cli.commands.main.compile_outputs._test_types import (
    CliJsonReportTestCase,
    JsonReportErrorTestCase,
    JsonReportTextTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.compile_outputs.helpers import (
    COMPILE_OUTPUTS_PREFIX,
    SURROGATE_HOOK_FILES,
    SURROGATE_SELECTOR,
    compile_json_text,
    record_output_work,
    write_files,
)

CLI_LOGGER: str = "sqlbuild.cli"
_ORJSON_EMITTERS: dict[bool, Callable[[object], str | None]] = {
    True: native_module.emit_orjson_report,
    False: native_module.emit_json_report,
}


@pytest.mark.parametrize(
    "test_case",
    [
        JsonReportTextTestCase(
            description="plain values are written as orjson writes them",
            report={"name": "orders", "rows": [1, 2.5, None, True], "é": "é"},
            expected_text=orjson.dumps(
                {"name": "orders", "rows": [1, 2.5, None, True], "é": "é"},
                option=orjson.OPT_INDENT_2,
            ).decode(),
        ),
        JsonReportTextTestCase(
            description="a non-finite float is null, as orjson writes it",
            report={"ratio": float("nan")},
            expected_text=orjson.dumps(
                {"ratio": float("nan")}, option=orjson.OPT_INDENT_2
            ).decode(),
        ),
        JsonReportTextTestCase(
            description="the largest unsigned 64-bit integer stays with orjson",
            report={"rows": 2**64 - 1},
            expected_text=orjson.dumps({"rows": 2**64 - 1}, option=orjson.OPT_INDENT_2).decode(),
        ),
        JsonReportTextTestCase(
            description="a wider integer falls back to json.dumps for the whole report",
            report={"rows": 2**70, "é": "é"},
            expected_text=json.dumps({"rows": 2**70, "é": "é"}, indent=2),
        ),
        JsonReportTextTestCase(
            description="lone surrogates beside escapes, a non-BMP pair and a wide integer",
            report={"text": '"q"\\é\udcff\U0001f600\ud83d', "rows": 2**70},
            expected_text=json.dumps(
                {"text": '"q"\\é\udcff\U0001f600\ud83d', "rows": 2**70}, indent=2
            ),
        ),
        JsonReportTextTestCase(
            description="scalar keys fall back to json.dumps key text",
            report={1: "a", 1.5: "b", float("nan"): "c", None: "d", False: "e"},
            expected_text=json.dumps(
                {1: "a", 1.5: "b", float("nan"): "c", None: "d", False: "e"}, indent=2
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_report_values_when_emitting_natively_then_text_matches_the_shipped_encoders(
    test_case: JsonReportTextTestCase,
) -> None:
    assert native_module.emit_json_report(test_case.report) == test_case.expected_text


@pytest.mark.parametrize(
    "test_case",
    [
        JsonReportErrorTestCase(
            description="error report: lone surrogate",
            report={"message": "unknown selector 'x\udcff'"},
            orjson_only=True,
            expected_message="str is not valid UTF-8: surrogates not allowed",
        ),
        JsonReportErrorTestCase(
            description="error report: integer beyond 64 bits",
            report={"line": -(2**64)},
            orjson_only=True,
            expected_message="Integer exceeds 64-bit range",
        ),
        JsonReportErrorTestCase(
            description="error report: integer key",
            report={1: "orders"},
            orjson_only=True,
            expected_message="Dict key must be str",
        ),
        JsonReportErrorTestCase(
            description="error report: value neither encoder writes",
            report={"names": frozenset()},
            orjson_only=True,
            expected_message="Type is not JSON serializable: frozenset",
        ),
        JsonReportErrorTestCase(
            description="full report: value neither encoder writes",
            report={"names": frozenset()},
            orjson_only=False,
            expected_message="Object of type frozenset is not JSON serializable",
        ),
        JsonReportErrorTestCase(
            description="full report: key neither encoder writes",
            report={frozenset(): "orders"},
            orjson_only=False,
            expected_message="keys must be str, int, float, bool or None, not frozenset",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_report_value_the_shipped_encoder_rejects_when_emitting_then_same_type_error(
    test_case: JsonReportErrorTestCase,
) -> None:
    with pytest.raises(TypeError) as raised:
        _ = _ORJSON_EMITTERS[test_case.orjson_only](test_case.report)

    assert str(raised.value) == test_case.expected_message


@pytest.mark.parametrize(
    "test_case",
    [
        CliJsonReportTestCase(
            description="hook docstring with a lone surrogate",
            args=("--no-cache",),
            expected_fragment=(
                r'"description": "Notify \"q\" \\ caf\u00e9 '
                r'\udcff\ud83d\ude00\ud83d\ude00\ud83d end."'
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_lone_surrogate_in_full_report_when_compiling_json_then_native_writes_json_dumps_bytes(
    test_case: CliJsonReportTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_files(project_dir=tmp_path, files=SURROGATE_HOOK_FILES)
    counts: Counter[str] = record_output_work(
        monkeypatch=monkeypatch, engine="native", reuse_disabled="1"
    )

    text: str = compile_json_text(project_dir=tmp_path, args=test_case.args, capsys=capsys)

    assert test_case.expected_fragment in text
    assert text.isascii()
    assert text == json.dumps(json.loads(text), indent=2) + "\n"
    assert counts[f"{COMPILE_OUTPUTS_PREFIX}json_reports"] == 1
    assert not hasattr(output_module, "json")
    assert not hasattr(output_module, "orjson")


@pytest.mark.parametrize(
    "test_case",
    [
        CliJsonReportTestCase(
            description="selector with undecodable bytes",
            args=("--no-cache", "--select", SURROGATE_SELECTOR),
            expected_fragment="str is not valid UTF-8: surrogates not allowed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_lone_surrogate_in_error_report_when_compiling_json_then_orjson_error_propagates(
    test_case: CliJsonReportTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.CRITICAL, logger=CLI_LOGGER)
    write_files(project_dir=tmp_path, files=SURROGATE_HOOK_FILES)
    _ = record_output_work(monkeypatch=monkeypatch, engine="native", reuse_disabled="1")

    with pytest.raises(TypeError) as raised:
        _ = compile_json_text(project_dir=tmp_path, args=test_case.args, capsys=capsys)
    _ = capsys.readouterr()

    assert str(raised.value) == test_case.expected_fragment


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
