from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.testing.check_test_conventions import main
from tests.unit.scripts.testing.check_test_conventions._test_types import (
    CheckCliMainTestCase,
    CheckPathsTestCase,
)
from tests.unit.scripts.testing.check_test_conventions.helpers import (
    base_repo_files,
    collect_violation_codes,
    collect_violation_messages,
    compliant_repo_files,
)

TEST_CASES: list[CheckPathsTestCase] = [
    CheckPathsTestCase(
        description="reports no violations for a compliant repo slice",
        repo_files=compliant_repo_files(),
        expected_violation_codes=(),
    ),
    CheckPathsTestCase(
        description="allows test helpers module name",
        repo_files=base_repo_files()
        | {
            "tests/unit/scripts/example_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ParseNameTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/example_tool/_test_helpers.py": dedent(
                """
                def normalize_name(raw_name: str) -> str:
                    return raw_name.strip()
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
                f"""
                import pytest

                from tests.unit.scripts.example_tool._test_types import ParseNameTestCase
                from tests.unit.scripts.example_tool._test_helpers import normalize_name


                @pytest.mark.parametrize(
                    "test_case",
                    [
                        ParseNameTestCase(
                            description="strips surrounding whitespace",
                            raw_name="  alice  ",
                            expected_result="alice",
                        )
                    ],
                    ids=["strips surrounding whitespace"],
                )
                def {
                    "test_given_name_with_surrounding_whitespace_when_parsing_then_returns_"
                    "trimmed_name"
                }(
                    test_case: ParseNameTestCase,
                ) -> None:
                    result = normalize_name(test_case.raw_name)

                    assert result == test_case.expected_result
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=(),
    ),
    CheckPathsTestCase(
        description="allows multi-case module constants ending with test cases",
        repo_files=base_repo_files()
        | {
            "tests/unit/scripts/example_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
                """
                import pytest

                from tests.unit.scripts.example_tool._test_types import ExampleTestCase


                PARSE_NAME_TEST_CASES = [
                    ExampleTestCase(
                        description="alice stays alice",
                        raw_name="alice",
                        expected_result="alice",
                    ),
                    ExampleTestCase(
                        description="bob stays bob",
                        raw_name="bob",
                        expected_result="bob",
                    ),
                ]


                @pytest.mark.parametrize(
                    "test_case",
                    PARSE_NAME_TEST_CASES,
                    ids=[case.description for case in PARSE_NAME_TEST_CASES],
                )
                def test_given_name_input_when_running_then_accepts_suffix_case_lists(
                    test_case: ExampleTestCase,
                ) -> None:
                    result = test_case.raw_name

                    assert result == test_case.expected_result
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=(),
    ),
    CheckPathsTestCase(
        description="reports missing local test types file",
        repo_files=base_repo_files()
        | {
            "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
                """
                def test_given_any_state_when_running_then_reports_missing_test_types() -> None:
                    assert True
                """
            ).strip()
            + "\n"
        },
        expected_violation_codes=("TC026",),
    ),
    CheckPathsTestCase(
        description="reports bad local test type fields",
        repo_files=base_repo_files()
        | {
            "tests/unit/scripts/example_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class InvalidCase:
                    raw_name: str
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
                """
                import pytest

                from tests.unit.scripts.example_tool._test_types import InvalidCase


                @pytest.mark.parametrize(
                    "test_case",
                    [InvalidCase(raw_name="alice")],
                    ids=["missing-required-fields"],
                )
                def test_given_invalid_case_when_running_then_surfaces_type_violations(
                    test_case: InvalidCase,
                ) -> None:
                    assert test_case.raw_name == "alice"
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=("TC003", "TC004", "TC011"),
    ),
    CheckPathsTestCase(
        description="reports non local imports and multi case inline parameterization",
        repo_files=base_repo_files()
        | {
            "tests/unit/scripts/example_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/other_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class OtherTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
                """
                import pytest

                from tests.unit.scripts.other_tool._test_types import OtherTestCase


                @pytest.mark.parametrize(
                    "test_case",
                    [
                        OtherTestCase(
                            description="alice stays alice",
                            raw_name="alice",
                            expected_result="alice",
                        ),
                        OtherTestCase(
                            description="bob stays bob",
                            raw_name="bob",
                            expected_result="bob",
                        ),
                    ],
                    ids=["alice stays alice", "bob stays bob"],
                )
                def test_given_name_input_when_running_then_reports_shape_violations(
                    test_case: OtherTestCase,
                ) -> None:
                    result = test_case.raw_name

                    assert result == test_case.expected_result
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=("TC005", "TC010", "TC022", "TC025"),
    ),
    CheckPathsTestCase(
        description="reports missing ids for module level test cases",
        repo_files=base_repo_files()
        | {
            "tests/unit/scripts/example_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
                """
                import pytest

                from tests.unit.scripts.example_tool._test_types import ExampleTestCase


                TEST_CASES = [
                    ExampleTestCase(
                        description="alice stays alice",
                        raw_name="alice",
                        expected_result="alice",
                    ),
                    ExampleTestCase(
                        description="bob stays bob",
                        raw_name="bob",
                        expected_result="bob",
                    ),
                ]


                @pytest.mark.parametrize("test_case", TEST_CASES)
                def test_given_name_input_when_running_then_requires_explicit_ids(
                    test_case: ExampleTestCase,
                ) -> None:
                    result = test_case.raw_name

                    assert result == test_case.expected_result
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=("TC014", "TC020"),
    ),
    CheckPathsTestCase(
        description="allows generated engine matrix in selection staleness e2e",
        repo_files=base_repo_files()
        | {
            "src/sqlbuild/cli/__init__.py": '"""CLI package."""\n',
            "tests/e2e/src/sqlbuild/cli/commands/main/selection_staleness/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class SelectionStalenessEngineE2ETestCase:
                    description: str
                    expected_rows_after_repair: tuple[tuple[object, ...], ...]
                """
            ).strip()
            + "\n",
            (
                "tests/e2e/src/sqlbuild/cli/commands/main/selection_staleness/"
                "test_selection_staleness.py"
            ): (
                "import pytest\n\n"
                "from tests.e2e.src.sqlbuild.cli.commands.main.selection_staleness."
                "_test_types import (\n"
                "    SelectionStalenessEngineE2ETestCase,\n"
                ")\n\n\n"
                'BASE_DESCRIPTIONS = ("native", "dbt")\n'
                "TEST_CASES = [\n"
                "    SelectionStalenessEngineE2ETestCase(\n"
                '        description=f"{description}: direct parent",\n'
                "        expected_rows_after_repair=((1, 1.25),),\n"
                "    )\n"
                "    for description in BASE_DESCRIPTIONS\n"
                "]\n"
                "@pytest.mark.parametrize(\n"
                '    "test_case",\n'
                "    TEST_CASES,\n"
                "    ids=[case.description for case in TEST_CASES],\n"
                ")\n"
                "def test_given_exact_selection_when_changed_then_preserves_contract(\n"
                "    test_case: SelectionStalenessEngineE2ETestCase,\n"
                ") -> None:\n"
                "    assert test_case.expected_rows_after_repair\n"
            ),
        },
        expected_violation_codes=(),
    ),
    CheckPathsTestCase(
        description="reports top level helper function in test module",
        repo_files=base_repo_files()
        | {
            "tests/unit/scripts/example_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
                """
                import pytest

                from tests.unit.scripts.example_tool._test_types import ExampleTestCase


                def normalize_name(raw_name: str) -> str:
                    return raw_name.strip()


                @pytest.mark.parametrize(
                    "test_case",
                    [
                        ExampleTestCase(
                            description="strips surrounding whitespace",
                            raw_name="  alice  ",
                            expected_result="alice",
                        )
                    ],
                    ids=["strips surrounding whitespace"],
                )
                def test_given_name_with_whitespace_when_parsing_then_returns_trimmed_name(
                    test_case: ExampleTestCase,
                ) -> None:
                    result = normalize_name(test_case.raw_name)

                    assert result == test_case.expected_result
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=("TC027",),
    ),
    CheckPathsTestCase(
        description="reports if statements inside test functions",
        repo_files=base_repo_files()
        | {
            "tests/unit/scripts/example_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
                """
                import pytest

                from tests.unit.scripts.example_tool._test_types import ExampleTestCase


                @pytest.mark.parametrize(
                    "test_case",
                    [
                        ExampleTestCase(
                            description="strips surrounding whitespace",
                            raw_name="  alice  ",
                            expected_result="alice",
                        )
                    ],
                    ids=["strips surrounding whitespace"],
                )
                def test_given_name_with_whitespace_when_parsing_then_reports_conditional_logic(
                    test_case: ExampleTestCase,
                ) -> None:
                    result = test_case.raw_name.strip()

                    if result == "alice":
                        assert result == test_case.expected_result
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=("TC036",),
    ),
    CheckPathsTestCase(
        description="reports invalid test scope",
        repo_files=base_repo_files()
        | {
            "tests/random/scripts/example_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/random/scripts/example_tool/test_parse_name.py": dedent(
                """
                import pytest

                from tests.random.scripts.example_tool._test_types import ExampleTestCase


                @pytest.mark.parametrize(
                    "test_case",
                    [
                        ExampleTestCase(
                            description="strips surrounding whitespace",
                            raw_name="  alice  ",
                            expected_result="alice",
                        )
                    ],
                    ids=["strips surrounding whitespace"],
                )
                def test_given_name_with_whitespace_when_parsing_then_returns_trimmed_name(
                    test_case: ExampleTestCase,
                ) -> None:
                    assert test_case.raw_name.strip() == test_case.expected_result
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=("TC029",),
    ),
    CheckPathsTestCase(
        description="reports invalid src mirroring depth",
        repo_files=base_repo_files()
        | {
            "tests/unit/src/example_pkg/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/unit/src/example_pkg/test_parse_name.py": dedent(
                """
                import pytest

                from tests.unit.src.example_pkg._test_types import ExampleTestCase


                @pytest.mark.parametrize(
                    "test_case",
                    [
                        ExampleTestCase(
                            description="strips surrounding whitespace",
                            raw_name="  alice  ",
                            expected_result="alice",
                        )
                    ],
                    ids=["strips surrounding whitespace"],
                )
                def test_given_name_with_whitespace_when_parsing_then_returns_trimmed_name(
                    test_case: ExampleTestCase,
                ) -> None:
                    assert test_case.raw_name.strip() == test_case.expected_result
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=("TC031",),
    ),
    CheckPathsTestCase(
        description="reports invalid scripts mirroring area",
        repo_files=base_repo_files()
        | {
            "tests/unit/scripts/missing_tool/_test_types.py": dedent(
                """
                from dataclasses import dataclass


                @dataclass(frozen=True)
                class ExampleTestCase:
                    description: str
                    raw_name: str
                    expected_result: str
                """
            ).strip()
            + "\n",
            "tests/unit/scripts/missing_tool/test_parse_name.py": dedent(
                """
                import pytest

                from tests.unit.scripts.missing_tool._test_types import ExampleTestCase


                @pytest.mark.parametrize(
                    "test_case",
                    [
                        ExampleTestCase(
                            description="strips surrounding whitespace",
                            raw_name="  alice  ",
                            expected_result="alice",
                        )
                    ],
                    ids=["strips surrounding whitespace"],
                )
                def test_given_name_with_whitespace_when_parsing_then_returns_trimmed_name(
                    test_case: ExampleTestCase,
                ) -> None:
                    assert test_case.raw_name.strip() == test_case.expected_result
                """
            ).strip()
            + "\n",
        },
        expected_violation_codes=("TC035",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_repo_slice_when_checking_paths_then_returns_expected_violation_codes(
    test_case: CheckPathsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    violation_codes: tuple[str, ...] = collect_violation_codes(tmp_path)

    assert violation_codes == test_case.expected_violation_codes


@pytest.mark.parametrize(
    "test_case",
    [
        CheckPathsTestCase(
            description="TC036 message recommends split tests over hidden helper branches",
            repo_files=base_repo_files()
            | {
                "tests/unit/scripts/example_tool/_test_types.py": dedent(
                    """
                    from dataclasses import dataclass


                    @dataclass(frozen=True)
                    class ExampleTestCase:
                        description: str
                        raw_name: str
                        expected_result: str
                    """
                ).strip()
                + "\n",
                "tests/unit/scripts/example_tool/test_parse_name.py": dedent(
                    """
                    import pytest

                    from tests.unit.scripts.example_tool._test_types import ExampleTestCase


                    @pytest.mark.parametrize(
                        "test_case",
                        [
                            ExampleTestCase(
                                description="strips surrounding whitespace",
                                raw_name="  alice  ",
                                expected_result="alice",
                            )
                        ],
                        ids=["strips surrounding whitespace"],
                    )
                    def test_given_name_when_parsing_then_reports_conditional_logic(
                        test_case: ExampleTestCase,
                    ) -> None:
                        result = test_case.raw_name.strip()

                        if result == "alice":
                            assert result == test_case.expected_result
                    """
                ).strip()
                + "\n",
            },
            expected_violation_codes=("TC036",),
            expected_message_fragments=(
                "split distinct setup or assertion paths into separate test functions",
                "instead of hiding branches in helpers",
            ),
        )
    ],
    ids=["TC036 message recommends split tests over hidden helper branches"],
)
def test_given_if_statement_when_checking_paths_then_message_recommends_split_tests(
    test_case: CheckPathsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    violation_messages: tuple[str, ...] = collect_violation_messages(tmp_path)

    fragment: str
    for fragment in test_case.expected_message_fragments:
        assert fragment in violation_messages[0]


@pytest.mark.parametrize(
    "test_case",
    [
        CheckCliMainTestCase(
            description="returns zero for a compliant repo slice",
            repo_files=compliant_repo_files(),
            expected_exit_code=0,
        )
    ],
    ids=["returns zero for a compliant repo slice"],
)
def test_given_repo_slice_when_running_cli_main_then_returns_expected_exit_code(
    test_case: CheckCliMainTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    exit_code: int = main([str(tmp_path / "tests")])

    assert exit_code == test_case.expected_exit_code


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
