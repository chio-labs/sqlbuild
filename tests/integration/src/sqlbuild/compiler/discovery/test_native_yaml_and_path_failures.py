"""Discovery reads plain YAML and UTF-8 paths, and rejects anything else with one clear error."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    AuthoredFileFailureTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    discovery_failure_with_help,
    write_project,
)

_SOURCE_HEAD: bytes = b"sources:\n  - name: raw_orders\n"
_MODEL: bytes = b"MODEL ();\nSELECT 1 AS id"
_HELP: bool = True


@pytest.mark.parametrize(
    "test_case",
    [
        AuthoredFileFailureTestCase(
            description="block, flow, quoted, folded and literal values with anchors and merges",
            files=(
                (
                    "sources/raw.yml",
                    b"---\n# raw\n" + _SOURCE_HEAD + b"    description: >\n      Raw\n"
                    b"      orders.\n    meta: &m {owner: 'data', tags: [a, \"b\"]}\n"
                    b"  - name: raw_items\n    description: |\n      Items.\n"
                    b"    meta:\n      <<: *m\n      extra: ~\n",
                ),
            ),
        ),
        AuthoredFileFailureTestCase(
            description="invalid YAML names the file and position",
            files=(("sources/raw.yml", _SOURCE_HEAD + b"    description: [unclosed\n"),),
            expected_error="SourceParseError",
            expected_message=(
                "{project}/sources/raw.yml contains invalid YAML at line 4, column 1: while "
                "parsing a flow sequence, expected ',' or ']'"
            ),
        ),
        AuthoredFileFailureTestCase(
            description="a binary value is unsupported at its node",
            files=(("sources/raw.yml", _SOURCE_HEAD + b"    meta:\n      blob: !!binary aGk=\n"),),
            expected_error="SourceParseError",
            expected_message=(
                "{project}/sources/raw.yml uses YAML that SQLBuild does not support at line 4, "
                "column 22: values tagged !!binary"
            ),
            expected_help=_HELP,
        ),
        AuthoredFileFailureTestCase(
            description="a tab is unsupported at its character",
            files=(("sources/raw.yml", _SOURCE_HEAD + b'    description: "Raw\torders"\n'),),
            expected_error="SourceParseError",
            expected_message=(
                "{project}/sources/raw.yml uses YAML that SQLBuild does not support at line 3, "
                "column 22: tab characters"
            ),
            expected_help=_HELP,
        ),
        AuthoredFileFailureTestCase(
            description="a directive is unsupported at its line",
            files=(("sources/raw.yml", b"%YAML 1.1\n---\nsources: []\n"),),
            expected_error="SourceParseError",
            expected_message=(
                "{project}/sources/raw.yml uses YAML that SQLBuild does not support at line 1, "
                "column 1: %YAML and %TAG directives"
            ),
            expected_help=_HELP,
        ),
        AuthoredFileFailureTestCase(
            description="a recursive alias is unsupported at the alias",
            files=(("sources/raw.yml", b"sources: []\nmeta: &a [*a]\n"),),
            expected_error="SourceParseError",
            expected_message=(
                "{project}/sources/raw.yml uses YAML that SQLBuild does not support at line 2, "
                "column 11: recursive aliases"
            ),
            expected_help=_HELP,
        ),
        AuthoredFileFailureTestCase(
            description="an invalid schema file fails as a schema file",
            files=(("models/marts/schema.yml", b"models: [\n"),),
            expected_error="SchemaParseError",
            expected_message=(
                "{project}/models/marts/schema.yml contains invalid YAML at line 2, column 1: "
                "while parsing a node, did not find expected node content"
            ),
        ),
        AuthoredFileFailureTestCase(
            description="names discovery never reads may be any bytes",
            files=(
                ("models/orders.sql", _MODEL),
                (os.fsdecode(b"models/notes\xe9.txt"), b"x"),
                (os.fsdecode(b"models/old\xe9/readme.md"), b"x"),
                (os.fsdecode(b"macros/x\xe9.txt"), b"x"),
                (os.fsdecode(b"tests/unit/x\xe9.txt"), b"x"),
                (os.fsdecode(b"tests/scenarios/x\xe9.md"), b"x"),
                (os.fsdecode(b"sources/x\xe9.txt"), b"x"),
                (os.fsdecode(b"seeds/x\xe9.txt"), b"x"),
                (os.fsdecode(b"data\xe9.csv"), b"x"),
                (os.fsdecode(b"target/x\xe9"), b"x"),
            ),
        ),
        AuthoredFileFailureTestCase(
            description="a model below a directory that is not UTF-8 is shown lossily",
            files=((os.fsdecode(b"models/old\xe9/orders.sql"), _MODEL),),
            expected_error="ProjectPathError",
            expected_message=(
                "Project path {project}/models/old\\xe9/orders.sql is not valid UTF-8; rename it "
                "so SQLBuild can read it"
            ),
        ),
        AuthoredFileFailureTestCase(
            description="a unit test path that is not UTF-8 is shown lossily",
            files=((os.fsdecode(b"tests/unit/caf\xe9.sql"), b'TEST (name "t");\nSELECT 1\n'),),
            expected_error="ProjectPathError",
            expected_message=(
                "Project path {project}/tests/unit/caf\\xe9.sql is not valid UTF-8; rename it so "
                "SQLBuild can read it"
            ),
        ),
        AuthoredFileFailureTestCase(
            description="a source path that is not UTF-8 is shown lossily",
            files=((os.fsdecode(b"sources/caf\xe9.yml"), _SOURCE_HEAD),),
            expected_error="ProjectPathError",
            expected_message=(
                "Project path {project}/sources/caf\\xe9.yml is not valid UTF-8; rename it so "
                "SQLBuild can read it"
            ),
        ),
        AuthoredFileFailureTestCase(
            description="a model path that is not UTF-8 is shown lossily",
            files=((os.fsdecode(b"models/caf\xe9.sql"), b"MODEL ();\nSELECT 1 AS id"),),
            expected_error="ProjectPathError",
            expected_message=(
                "Project path {project}/models/caf\\xe9.sql is not valid UTF-8; rename it so "
                "SQLBuild can read it"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_authored_files_when_discovering_then_plain_yaml_loads_and_the_rest_fails_clearly(
    test_case: AuthoredFileFailureTestCase, tmp_path: Path
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)

    failure: tuple[str, str, bool] = discovery_failure_with_help(project_dir=tmp_path)

    assert failure == (
        test_case.expected_error,
        test_case.expected_message.format(project=tmp_path),
        test_case.expected_help,
    ), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
