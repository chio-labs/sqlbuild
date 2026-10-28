"""Capture the expected rows of DuckShop's edge-case unit tests from Snowflake.

Run it from `benchmarks/duckshop/project` with the `edge` target configured (see RUNBOOK.md,
step 7):

    python ../scripts/capture_edge_expectations.py [--write] [TEST_NAME ...]

It compiles the project and runs the edge-case unit tests on the `edge` target, which writes each
test's executed SQL to `target/run/tests/`; the newest file per test is read. For every
`__expected__<model>` CTE of the selected tests (all edge-case tests by default), it then runs the
model under test on its fixtures, reads the actual rows of the columns the CTE lists, and renders
them as typed SQL literals in a stable order. Without `--write` it prints them; with `--write` it
replaces the CTE body in the test file. Review every captured value before committing it: a
capture records what Snowflake returned, right or wrong.

The script reads the executed test SQL that SQLBuild writes, so a change to that SQL's shape may
need a change here.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import unicodedata

SQB = os.environ.get("SQB", "sqb")
TARGET = "edge"
LITERAL_WIDTH = 90
TEST_HEADER = re.compile(r'^TEST \(\s*name "([^"]+)"', re.MULTILINE)
EXPECTED_COLUMNS = re.compile(r"\(SELECT ((?:(?!SELECT).)*?) FROM __actual__(\w+) EXCEPT")
STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.|'')*'")
ESCAPED_CATEGORIES = ("Cc", "Cf", "Mn", "Zl", "Zp")


def run_sqb(project: pathlib.Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SQB, "--no-color", *arguments],
        cwd=project,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def query(project: pathlib.Path, sql: str) -> list[dict[str, object]]:
    path = project / "target" / "capture_query.sql"
    path.write_text(sql)
    result = run_sqb(
        project, "query", "--target", TARGET, "--file", str(path), "--json", "--no-limit"
    )
    documents = [line for line in result.stdout.splitlines() if line.startswith("[")]
    if result.returncode != 0 or not documents:
        raise RuntimeError(f"query failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}")
    return json.loads(documents[-1])


def test_blocks(text: str) -> list[tuple[str, int, int]]:
    """(name, start, end) of every TEST block in a test file."""

    starts = list(TEST_HEADER.finditer(text))
    return [
        (match.group(1), match.start(), starts[i + 1].start() if i + 1 < len(starts) else len(text))
        for i, match in enumerate(starts)
    ]


def executed_test_sql(project: pathlib.Path, name: str) -> tuple[str, str]:
    """The fixture and model CTEs of an executed test, and its final comparison SELECT."""

    hits = list((project / "target" / "run" / "tests").rglob(f"{name}.sql"))
    if not hits:
        raise RuntimeError(f"no executed SQL for {name}")
    sql = max(hits, key=lambda hit: hit.stat().st_mtime).read_text()
    comparison = re.search(r"\nSELECT \d+ AS step_index", sql)
    if comparison is None:
        raise RuntimeError(f"no comparison SELECT in the executed SQL of {name}")
    return sql[: comparison.start()], sql[comparison.start() :]


def render_expression(column: str, snowflake_type: str) -> str:
    """Select a column as text that round-trips exactly through a typed literal."""

    base = snowflake_type.split("[")[0].split("(")[0]
    formats = {
        "DATE": "YYYY-MM-DD",
        "TIME": "HH24:MI:SS.FF9",
        "TIMESTAMP_NTZ": "YYYY-MM-DD HH24:MI:SS.FF9",
        "TIMESTAMP_TZ": "YYYY-MM-DD HH24:MI:SS.FF9 TZH:TZM",
        "TIMESTAMP_LTZ": "YYYY-MM-DD HH24:MI:SS.FF9 TZH:TZM",
    }
    if base == "FLOAT":
        return column
    if base == "NUMBER":
        return f"TO_VARCHAR({column})"
    if base in formats:
        return f"TO_VARCHAR({column}, '{formats[base]}')"
    if base in ("VARIANT", "OBJECT", "ARRAY"):
        return f"TO_JSON({column})"
    if base == "BINARY":
        return f"HEX_ENCODE({column})"
    return f"{column}::VARCHAR"


def quote(text: str) -> str:
    """A Snowflake string literal, escaping characters that are invisible or easily confused."""

    out = []
    for char in text:
        if char == "\\":
            out.append("\\\\")
        elif char == "'":
            out.append("''")
        elif ord(char) <= 0xFFFF and unicodedata.category(char) in ESCAPED_CATEGORIES:
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    return "'" + "".join(out) + "'"


def literal(value: object, snowflake_type: str) -> str:
    sql_type = snowflake_type.split("[")[0]
    if sql_type.startswith("VARCHAR"):
        sql_type = "VARCHAR"
    base = sql_type.split("(")[0]
    if value is None:
        return "NULL" if base == "NULL" else f"CAST(NULL AS {sql_type})"
    if base == "FLOAT":
        return f"'{value if isinstance(value, str) else repr(float(value))}'::FLOAT"  # type: ignore[arg-type]
    if base == "NUMBER":
        scale = re.match(r"NUMBER\(\d+,(\d+)\)", sql_type)
        return f"{value}::{sql_type}" if scale and scale.group(1) != "0" else str(value)
    if base == "BOOLEAN":
        return "TRUE" if str(value).lower() == "true" else "FALSE"
    if base == "DATE":
        return f"'{value}'::DATE"
    if base in ("TIME", "TIMESTAMP_NTZ", "TIMESTAMP_TZ", "TIMESTAMP_LTZ"):
        text = re.sub(
            r"\.(\d*?)0+(?=$| )", lambda m: f".{m.group(1)}" if m.group(1) else "", str(value)
        )
        return f"'{text}'::{sql_type}"
    if base == "VARIANT":
        return f"PARSE_JSON({quote(str(value))})"
    if base in ("OBJECT", "ARRAY"):
        return f"PARSE_JSON({quote(str(value))})::{base}"
    if base == "BINARY":
        return f"HEX_DECODE_BINARY('{value}')"
    return quote(str(value))


def capture(project: pathlib.Path, ctes: str, model: str, columns: list[str]) -> str | None:
    """The actual rows of a model's listed columns, as the body of its expected CTE."""

    probe = ", ".join(f"SYSTEM$TYPEOF({column}) AS t{i}" for i, column in enumerate(columns))
    typed = query(project, f"{ctes}\nSELECT {probe} FROM __actual__{model} LIMIT 1")
    if not typed:
        return None
    types = [str(typed[0][f"T{i}"]) for i in range(len(columns))]
    rendered = ", ".join(
        f"{render_expression(column, kind)} AS v{i}"
        for i, (column, kind) in enumerate(zip(columns, types, strict=True))
    )
    rows = query(project, f"{ctes}\nSELECT {rendered} FROM __actual__{model}")
    values = sorted([literal(row[f"V{i}"], kind) for i, kind in enumerate(types)] for row in rows)
    selects = [
        "SELECT\n" + ",\n".join(f"    {v} AS {c}" for v, c in zip(row, columns, strict=True))
        for row in values
    ]
    return "\n  UNION ALL\n  ".join(selects)


def replace_expected(text: str, start: int, end: int, model: str, body: str) -> str:
    match = re.compile(rf"__expected__{model} AS \(\n").search(text, start, end)
    if match is None:
        raise RuntimeError(f"no __expected__{model} CTE")
    depth, index, in_string = 1, match.end(), False
    while depth:
        char = text[index]
        if in_string:
            if char == "\\":
                index += 1
            elif char == "'":
                in_string = False
        elif char == "'":
            in_string = True
        elif char in "()":
            depth += 1 if char == "(" else -1
        index += 1
    return text[: match.end()] + "  " + body + "\n" + text[index - 1 :]


def wrap_literal(text: str, indent: str) -> str:
    """Split a long string literal into `||` parts, never inside an escape or doubled quote."""

    body, parts = text[1:-1], []
    while len(body) > LITERAL_WIDTH:
        cut = body.rfind(", ", 0, LITERAL_WIDTH)
        cut = cut + 2 if cut > 0 else body.rfind(",", 0, LITERAL_WIDTH) + 1 or LITERAL_WIDTH
        escape = body.rfind("\\", max(0, cut - 6), cut)
        if escape >= 0:
            while escape > 0 and body[escape - 1] == "\\":
                escape -= 1
            cut = escape
        while body[cut - 1] == "'" and body[cut : cut + 1] == "'":
            cut -= 1
        parts.append(body[:cut])
        body = body[cut:]
    parts.append(body)
    return f"\n{indent}|| ".join(f"'{part}'" for part in parts)


def wrap_line(line: str) -> str:
    indent = line[: len(line) - len(line.lstrip())]
    return STRING_LITERAL.sub(
        lambda m: (
            wrap_literal(m.group(0), indent) if len(m.group(0)) > LITERAL_WIDTH + 10 else m.group(0)
        ),
        line,
    )


def wrap_long_literals(text: str) -> str:
    return "".join(wrap_line(line) for line in text.splitlines(keepends=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tests", nargs="*", help="test names to capture (default: all edge tests)")
    parser.add_argument("--write", action="store_true", help="write the rows into the test files")
    args = parser.parse_args()
    project = pathlib.Path.cwd()

    compiled = run_sqb(project, "compile")
    if " 0 errors" not in compiled.stdout + compiled.stderr:
        print((compiled.stdout + compiled.stderr)[-3000:], file=sys.stderr)
        return 1
    tested = run_sqb(project, "test", "--target", TARGET, "--select", "tag:edge_case")
    if "TOTAL=" not in tested.stdout + tested.stderr:
        print((tested.stdout + tested.stderr)[-3000:], file=sys.stderr)
        return 1

    failures = 0
    for path in sorted((project / "tests" / "unit").glob("*/edge_cases/*.sql")):
        for name, _, _ in test_blocks(path.read_text()):
            if args.tests and name not in args.tests:
                continue
            try:
                ctes, comparison = executed_test_sql(project, name)
            except RuntimeError as error:
                print(f"!! {name}: {error}", file=sys.stderr)
                failures += 1
                continue
            expected = {m.group(2): m.group(1) for m in EXPECTED_COLUMNS.finditer(comparison)}
            for model, listed in expected.items():
                columns = [column.strip() for column in listed.split(",")]
                try:
                    body = capture(project, ctes, model, columns)
                except RuntimeError as error:
                    print(f"!! {name} {model}: {error}", file=sys.stderr)
                    failures += 1
                    continue
                print(f"== {name} {model}\n  {body or '(no rows)'}\n")
                if args.write and body is not None:
                    text = path.read_text()
                    _, start, end = next(b for b in test_blocks(text) if b[0] == name)
                    path.write_text(
                        wrap_long_literals(replace_expected(text, start, end, model, body))
                    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
