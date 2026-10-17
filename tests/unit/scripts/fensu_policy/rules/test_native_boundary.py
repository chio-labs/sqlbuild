from textwrap import dedent

import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy._helpers.native_crossings import crossing_lines, python_field_lines
from scripts.fensu_policy.rules.native_boundary import native_module_test_patch
from tests.unit.scripts.fensu_policy.rules._test_types import (
    NativeLinesTestCase,
    NativePatchTestCase,
)

TEST_PATH: str = "tests/unit/src/sqlbuild/example/test_example.py"


@pytest.mark.parametrize(
    "test_case",
    [
        NativePatchTestCase(
            description="aliased native module patch faults",
            source=dedent(
                """
                import sqlbuild._native as native_module


                def test_example(monkeypatch: object) -> None:
                    monkeypatch.setattr(native_module, "plan", None)
                """
            ),
            expected_fault_count=1,
        ),
        NativePatchTestCase(
            description="from-imported native module patch faults",
            source=dedent(
                """
                from unittest import mock

                from sqlbuild import _native


                def test_example() -> None:
                    with mock.patch.object(_native, "plan"):
                        pass
                """
            ),
            expected_fault_count=1,
        ),
        NativePatchTestCase(
            description="string native patch target faults",
            source=dedent(
                """
                from unittest import mock


                def test_example() -> None:
                    with mock.patch("sqlbuild._native.plan"):
                        pass
                """
            ),
            expected_fault_count=1,
        ),
        NativePatchTestCase(
            description="patching another module passes",
            source=dedent(
                """
                import sqlbuild.executor.runtime as runtime_module


                def test_example(monkeypatch: object) -> None:
                    monkeypatch.setattr(runtime_module, "run", None)
                """
            ),
            expected_fault_count=0,
        ),
        NativePatchTestCase(
            description="budgeted native patch passes",
            source=dedent(
                """
                import sqlbuild._native as native_module


                def test_example(monkeypatch: object) -> None:
                    monkeypatch.setattr(native_module, "plan", None)
                """
            ),
            expected_fault_count=0,
            budgets=(f"{TEST_PATH}=1",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_test_module_when_checking_native_patches_then_matches_contract(
    test_case: NativePatchTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=native_module_test_patch,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=TEST_PATH,
            scope_root=None,
        ),
        rule_options={"pending_budgets": test_case.budgets},
    )

    assert result.fault_count == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        NativeLinesTestCase(
            description="attribute reads, calls, imports and module strings count",
            source=dedent(
                """
                fn read(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<()> {
                    let name = value.getattr("name")?;
                    let _ = value.call_method1("get", ("x",))?;
                    let _ = imported(py, "pathlib", "Path")?.call1((name,))?;
                    let _ = py.import("sqlbuild.compiler")?;
                    Ok(())
                }
                """
            ),
            expected_lines=(3, 4, 5, 5, 6, 6),
        ),
        NativeLinesTestCase(
            description="comments, imports and test modules are skipped",
            source=dedent(
                """
                use pyo3::types::PyAnyMethods;
                // value.getattr("name")
                fn read() {}

                #[cfg(test)]
                mod tests {
                    fn probe(value: &Bound<'_, PyAny>) { let _ = value.getattr("x"); }
                }
                """
            ),
            expected_lines=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rust_source_when_finding_crossings_then_reports_each_crossing(
    test_case: NativeLinesTestCase,
) -> None:
    assert tuple(crossing_lines(source=test_case.source)) == test_case.expected_lines


@pytest.mark.parametrize(
    "test_case",
    [
        NativeLinesTestCase(
            description="Python-typed struct fields count and Rust fields do not",
            source=dedent(
                """
                pub(crate) struct Request<'py> {
                    pub(crate) project: Bound<'py, PyAny>,
                    pub(crate) options: Py<PyDict>,
                    pub(crate) name: String,
                    pub(crate) adapter: Option<Py<PyAny>>,
                }
                """
            ),
            expected_lines=(3, 4, 6),
        ),
        NativeLinesTestCase(
            description="Python-typed function parameters do not count",
            source=dedent(
                """
                fn read(value: &Bound<'_, PyAny>) -> PyResult<String> {
                    Ok(String::new())
                }
                """
            ),
            expected_lines=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rust_source_when_finding_python_fields_then_reports_struct_fields(
    test_case: NativeLinesTestCase,
) -> None:
    assert tuple(python_field_lines(source=test_case.source)) == test_case.expected_lines
