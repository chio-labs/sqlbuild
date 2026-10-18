//! The `checks` and `scenarios` entries of execution-result documents.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyListMethods, PyTuple};

use crate::bindings::_helpers::plan_output::values::{any, dict, items, text};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::result_output::assets::{or_none, without_none};
use crate::bindings::_helpers::result_output::projection::{
    Projection, audit_check_id, rounded, sql_test_check_id,
};

const PASS_OUTCOME: &str = "pass";
const INSUFFICIENT_OUTCOME: &str = "insufficient";
const MEASUREMENT_MODE: &str = "measurement";
const SUCCESS_STATUS: &str = "success";
const DECIMAL_KIND: &str = "decimal";
const SCALAR_KINDS: [&str; 5] = ["string", "integer", "boolean", "float", "null"];
const COLLECTION_KINDS: [&str; 2] = ["list", "set"];
const ERROR_FIELDS: [&str; 3] = ["error_code", "error_help", "error_message"];
const EXPECTED_COUNT_FIELDS: [&str; 4] = [
    "actual_row_count",
    "expected_row_count",
    "mismatched_row_count",
    "missing_row_count",
];
const COMPARISON_COMPLETED: &str = "completed";
const COMPARISON_NOT_RUN: &str = "not_run";

fn value<'py>(result: &Bound<'py, PyAny>, field: &str) -> PyResult<Bound<'py, PyAny>> {
    native_field(&native_field(result, field)?, "value")
}

fn optional_value<'py>(result: &Bound<'py, PyAny>, field: &str) -> PyResult<Bound<'py, PyAny>> {
    let value: Bound<'py, PyAny> = native_field(result, field)?;
    if value.is_none() {
        return Ok(value);
    }
    native_field(&value, "value")
}

fn fields<'py>(
    result: &Bound<'py, PyAny>,
    names: &[&'static str],
) -> PyResult<Vec<(&'static str, Bound<'py, PyAny>)>> {
    names
        .iter()
        .map(|name| Ok((*name, native_field(result, name)?)))
        .collect()
}

fn tuple_of<'py>(py: Python<'py>, entries: Vec<Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyTuple::new(py, entries)?.into_any())
}

/// A SQL value as plain JSON: decimals as text, collections as lists, structs as objects.
fn sql_value_json<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = value.py();
    let kind: String = text(&native_field(&native_field(value, "kind")?, "value")?)?;
    let inner: Bound<'py, PyAny> = native_field(value, "value")?;
    if kind == DECIMAL_KIND {
        return Ok(inner.str()?.into_any());
    }
    if SCALAR_KINDS.contains(&kind.as_str()) {
        return Ok(inner);
    }
    if COLLECTION_KINDS.contains(&kind.as_str()) {
        let list: Bound<'py, PyList> = PyList::empty(py);
        for item in items(&inner)? {
            list.append(sql_value_json(&item)?)?;
        }
        return Ok(list.into_any());
    }
    let object: Bound<'py, PyDict> = PyDict::new(py);
    for item in items(&inner)? {
        let (name, item): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item.extract()?;
        object.set_item(name, sql_value_json(&item)?)?;
    }
    Ok(object.into_any())
}

/// The case, schema and parameter values of a parameterized SQL test.
fn case_metadata<'py>(
    result: &Bound<'py, PyAny>,
) -> PyResult<Vec<(&'static str, Bound<'py, PyAny>)>> {
    let py: Python<'py> = result.py();
    let source_path: Bound<'py, PyAny> = native_field(result, "source_path")?;
    if native_field(result, "case_name")?.is_none() || source_path.is_none() {
        return Ok(Vec::new());
    }
    let parameter_types: Bound<'py, PyDict> = PyDict::new(py);
    let mut schema: Vec<Bound<'py, PyDict>> = Vec::new();
    for parameter in items(&native_field(result, "parameter_schema")?)? {
        let parameter_type: Bound<'py, PyAny> = value(&parameter, "value_type")?;
        parameter_types.set_item(native_field(&parameter, "name")?, &parameter_type)?;
        schema.push(dict(
            py,
            vec![
                ("name", native_field(&parameter, "name")?),
                ("type", parameter_type),
                ("nullable", native_field(&parameter, "nullable")?),
            ],
        )?);
    }
    let mut parameters: Vec<Bound<'py, PyDict>> = Vec::new();
    for item in items(&native_field(result, "parameter_values")?)? {
        let (name, parameter_value): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item.extract()?;
        let parameter_type: Bound<'py, PyAny> = parameter_types.as_any().get_item(&name)?;
        parameters.push(dict(
            py,
            vec![
                ("name", name),
                ("type", parameter_type),
                ("value", sql_value_json(&parameter_value)?),
            ],
        )?);
    }
    let mut metadata: Vec<(&'static str, Bound<'py, PyAny>)> =
        vec![("source_path", source_path.call_method0("as_posix")?)];
    metadata.extend(fields(
        result,
        &[
            "block_index",
            "parent_name",
            "case_name",
            "case_index",
            "case_fingerprint",
        ],
    )?);
    metadata.push(("parameter_schema", tuple_of(py, schema)?));
    metadata.push(("parameters", tuple_of(py, parameters)?));
    Ok(metadata)
}

fn difference_samples<'py>(samples: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = samples.py();
    let formatted: Bound<'py, PyList> = PyList::empty(py);
    for sample in items(samples)? {
        let pairs: Bound<'py, PyList> = PyList::empty(py);
        for pair in items(&native_field(&sample, "values")?)? {
            let (name, sample_value): (Bound<'py, PyAny>, Bound<'py, PyAny>) = pair.extract()?;
            pairs.append(dict(py, vec![("name", name), ("value", sample_value)])?)?;
        }
        formatted.append(pairs)?;
    }
    or_none(formatted.into_any())
}

fn sql_test_step<'py>(step: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = step.py();
    let differences: Bound<'py, PyList> = PyList::empty(py);
    for difference in items(&native_field(step, "column_differences")?)? {
        differences.append(dict(
            py,
            fields(&difference, &["name", "actual", "expected"])?,
        )?)?;
    }
    let mut entries: Vec<(&str, Bound<'py, PyAny>)> = vec![
        ("model_name", native_field(step, "model_name")?),
        ("status", value(step, "outcome")?),
    ];
    entries.extend(fields(
        step,
        &[
            "actual_row_count",
            "expected_row_count",
            "mismatched_row_count",
            "unexpected_row_count",
            "missing_row_count",
        ],
    )?);
    entries.push((
        "unexpected_samples",
        difference_samples(&native_field(step, "unexpected_samples")?)?,
    ));
    entries.push((
        "missing_samples",
        difference_samples(&native_field(step, "missing_samples")?)?,
    ));
    entries.push(("column_differences", or_none(differences.into_any())?));
    entries.extend(fields(
        step,
        &["error_code", "error_help", "error_message"],
    )?);
    without_none(py, entries)
}

/// SQL test checks with their steps and parameterized case metadata.
pub(crate) fn sql_test_checks<'py>(
    projection: &Projection<'py>,
    results: &[Bound<'py, PyAny>],
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let mut checks: Vec<Bound<'py, PyDict>> = Vec::new();
    for result in results {
        if !projection.terminal_recorded(result)? {
            continue;
        }
        let py: Python<'py> = result.py();
        let steps: Vec<Bound<'py, PyAny>> = items(&native_field(result, "step_results")?)?;
        let outcome: Bound<'py, PyAny> = value(result, "outcome")?;
        let mut entries: Vec<(&str, Bound<'py, PyAny>)> = vec![
            ("kind", any(py, "sql_test")?),
            ("name", native_field(result, "test_name")?),
            ("check_id", any(py, sql_test_check_id(result)?)?),
        ];
        entries.extend(case_metadata(result)?);
        entries.push(("passed", any(py, outcome.eq(PASS_OUTCOME)?)?));
        entries.push(("status", outcome));
        entries.push((
            "duration_ms",
            projection.result_duration(result, &py.None().into_bound(py))?,
        ));
        entries.push((
            "asset_name",
            match steps.first() {
                Some(step) => native_field(step, "model_name")?,
                None => py.None().into_bound(py),
            },
        ));
        entries.extend(fields(
            result,
            &["error_code", "error_help", "error_message"],
        )?);
        entries.push((
            "steps",
            tuple_of(
                py,
                steps.iter().map(sql_test_step).collect::<PyResult<_>>()?,
            )?,
        ));
        checks.push(without_none(py, entries)?);
    }
    Ok(checks)
}

fn threshold_bound<'py>(bound: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = bound.py();
    let rendered: Bound<'py, PyDict> = dict(py, vec![("operator", value(bound, "operator")?)])?;
    let limit: Bound<'py, PyAny> = native_field(bound, "limit")?;
    if limit.is_none() {
        rendered.set_item("lower", native_field(bound, "lower")?)?;
        rendered.set_item("upper", native_field(bound, "upper")?)?;
    } else {
        rendered.set_item("limit", limit)?;
    }
    Ok(rendered.into_any())
}

/// The warn and error bounds of measurement thresholds, or `None`.
pub(crate) fn measurement_thresholds<'py>(
    thresholds: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if thresholds.is_none() {
        return Ok(thresholds.clone());
    }
    let rendered: Bound<'py, PyDict> = PyDict::new(thresholds.py());
    for severity in ["warn", "error"] {
        let bound: Bound<'py, PyAny> = native_field(thresholds, severity)?;
        if !bound.is_none() {
            rendered.set_item(severity, threshold_bound(&bound)?)?;
        }
    }
    Ok(rendered.into_any())
}

/// `len(evidence_rows)` and `evidence_truncated` of a measurement audit, else `None`.
pub(crate) fn measurement_evidence<'py>(
    result: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py: Python<'py> = result.py();
    if !value(result, "evaluation_mode")?.eq(MEASUREMENT_MODE)? {
        return Ok((py.None().into_bound(py), py.None().into_bound(py)));
    }
    Ok((
        any(py, native_field(result, "evidence_rows")?.len()?)?,
        native_field(result, "evidence_truncated")?,
    ))
}

/// Whether an audit outcome counts as passed.
pub(crate) fn audit_passed(result: &Bound<'_, PyAny>) -> PyResult<bool> {
    let outcome: Bound<'_, PyAny> = value(result, "outcome")?;
    Ok(outcome.eq(PASS_OUTCOME)? || outcome.eq(INSUFFICIENT_OUTCOME)?)
}

/// Audit checks; `terminal_evidence` keeps results whose model already has a terminal.
pub(crate) fn audit_checks<'py>(
    projection: &Projection<'py>,
    results: &Bound<'py, PyAny>,
    terminal_evidence: bool,
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let mut checks: Vec<Bound<'py, PyDict>> = Vec::new();
    for result in items(results)? {
        if !terminal_evidence && !projection.terminal_recorded(&result)? {
            continue;
        }
        let py: Python<'py> = result.py();
        let (evidence_count, evidence_truncated) = measurement_evidence(&result)?;
        let mut entries: Vec<(&str, Bound<'py, PyAny>)> = vec![("kind", any(py, "audit")?)];
        entries.push(("name", native_field(&result, "audit_name")?));
        entries.extend(fields(
            &result,
            &["audit_definition_name", "audit_description", "audit_meta"],
        )?);
        entries.push(("check_id", any(py, audit_check_id(&result)?)?));
        entries.push(("passed", any(py, audit_passed(&result)?)?));
        entries.push(("status", value(&result, "outcome")?));
        entries.push(("severity", value(&result, "severity")?));
        entries.push(("row_count", native_field(&result, "row_count")?));
        entries.push(("attachment_kind", value(&result, "attachment_kind")?));
        entries.push((
            "attached_target_kind",
            optional_value(&result, "attached_target_kind")?,
        ));
        entries.push(("asset_name", native_field(&result, "attached_target_name")?));
        entries.push((
            "attached_column_name",
            native_field(&result, "attached_column_name")?,
        ));
        entries.push(("run_scope_phase", value(&result, "run_scope_phase")?));
        entries.push(("reused", native_field(&result, "reused")?));
        entries.push(("evaluation_mode", value(&result, "evaluation_mode")?));
        entries.extend(fields(
            &result,
            &[
                "measured_value",
                "sample_count",
                "sample_unit",
                "minimum_samples",
            ],
        )?);
        entries.push((
            "thresholds",
            measurement_thresholds(&native_field(&result, "thresholds")?)?,
        ));
        entries.push(("evidence_count", evidence_count));
        entries.push(("evidence_truncated", evidence_truncated));
        entries.push(("execution_error", native_field(&result, "execution_error")?));
        checks.push(without_none(py, entries)?);
    }
    Ok(checks)
}

/// `pass`, `warn` or `fail` of a Python check result.
pub(crate) fn python_check_status(result: &Bound<'_, PyAny>) -> PyResult<&'static str> {
    Ok(if native_field(result, "passed")?.is_truthy()? {
        "pass"
    } else if native_field(result, "warned")?.is_truthy()? {
        "warn"
    } else {
        "fail"
    })
}

/// Python check results.
pub(crate) fn python_checks<'py>(
    projection: &Projection<'py>,
    results: &[Bound<'py, PyAny>],
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let mut checks: Vec<Bound<'py, PyDict>> = Vec::new();
    for result in results {
        if !projection.terminal_recorded(result)? {
            continue;
        }
        let py: Python<'py> = result.py();
        let name: String = text(&native_field(result, "node_name")?)?;
        checks.push(without_none(
            py,
            vec![
                ("kind", any(py, "python_check")?),
                ("name", native_field(result, "node_name")?),
                ("check_id", any(py, format!("python_check:{name}"))?),
                ("passed", native_field(result, "passed")?),
                ("status", any(py, python_check_status(result)?)?),
                ("severity", value(result, "severity")?),
                ("message", native_field(result, "message")?),
                ("error_message", native_field(result, "error_message")?),
                ("metadata", native_field(result, "metadata")?),
                (
                    "warnings",
                    or_none(native_field(result, "warning_messages")?)?,
                ),
            ],
        )?);
    }
    Ok(checks)
}

fn with_errors<'py>(
    result: &Bound<'py, PyAny>,
    mut entries: Vec<(&'static str, Bound<'py, PyAny>)>,
) -> PyResult<Bound<'py, PyDict>> {
    entries.extend(fields(result, &ERROR_FIELDS)?);
    without_none(result.py(), entries)
}

/// The scenario check with its expected-result and assertion outcomes.
pub(crate) fn scenario_check<'py>(result: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = result.py();
    let name: String = text(&native_field(result, "scenario_name")?)?;
    let status: Bound<'py, PyAny> = value(result, "status")?;
    let mut expected: Vec<Bound<'py, PyDict>> = Vec::new();
    for item in items(&native_field(result, "expected_results")?)? {
        let counts: Vec<(&'static str, Bound<'py, PyAny>)> = fields(&item, &EXPECTED_COUNT_FIELDS)?;
        let compared: bool = counts.iter().all(|(_, count)| !count.is_none());
        let mut entries: Vec<(&'static str, Bound<'py, PyAny>)> = vec![
            ("model_name", native_field(&item, "model_name")?),
            ("status", value(&item, "status")?),
            (
                "comparison_status",
                any(
                    py,
                    if compared {
                        COMPARISON_COMPLETED
                    } else {
                        COMPARISON_NOT_RUN
                    },
                )?,
            ),
        ];
        entries.extend(counts);
        let result: Bound<'py, PyDict> = dict(py, entries)?;
        for (name, error) in fields(&item, &ERROR_FIELDS)? {
            if !error.is_none() {
                result.set_item(name, error)?;
            }
        }
        expected.push(result);
    }
    let mut assertions: Vec<Bound<'py, PyDict>> = Vec::new();
    for item in items(&native_field(result, "assertion_results")?)? {
        let failing: Bound<'py, PyAny> = native_field(&item, "failing_row_count")?;
        let ran: &str = if failing.is_none() {
            COMPARISON_NOT_RUN
        } else {
            COMPARISON_COMPLETED
        };
        let result: Bound<'py, PyDict> = dict(
            py,
            vec![
                ("name", native_field(&item, "name")?),
                ("status", value(&item, "status")?),
                ("query_status", any(py, ran)?),
                ("failing_row_count", failing),
                ("sample_rows", native_field(&item, "sample_rows")?),
            ],
        )?;
        for (name, error) in fields(&item, &ERROR_FIELDS)? {
            if !error.is_none() {
                result.set_item(name, error)?;
            }
        }
        assertions.push(result);
    }
    with_errors(
        result,
        vec![
            ("kind", any(py, "scenario")?),
            ("name", any(py, name.as_str())?),
            ("check_id", any(py, format!("sql_scenario:{name}"))?),
            ("passed", any(py, status.eq(SUCCESS_STATUS)?)?),
            ("status", status),
            ("expected_results", tuple_of(py, expected)?),
            ("assertion_results", tuple_of(py, assertions)?),
        ],
    )
}

fn rounded_duration<'py>(result: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let duration: Bound<'py, PyAny> = native_field(result, "duration_ms")?;
    if duration.is_none() {
        return Ok(duration);
    }
    rounded(result.py(), duration.extract()?)
}

/// The run outcome of one scenario.
pub(crate) fn scenario_result<'py>(result: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = result.py();
    let path: Bound<'py, PyAny> = native_field(result, "local_duckdb_path")?;
    let local_status: Bound<'py, PyAny> = native_field(result, "local_status")?;
    with_errors(
        result,
        vec![
            ("name", native_field(result, "scenario_name")?),
            ("status", value(result, "status")?),
            ("duration_ms", rounded_duration(result)?),
            (
                "local_status",
                if local_status.is_truthy()? {
                    native_field(&local_status, "value")?
                } else {
                    py.None().into_bound(py)
                },
            ),
            ("retained", native_field(result, "retained")?),
            (
                "local_duckdb_path",
                if path.is_truthy()? {
                    path.str()?.into_any()
                } else {
                    py.None().into_bound(py)
                },
            ),
        ],
    )
}

/// The capture outcome of one scenario snapshot sync or refresh.
pub(crate) fn snapshot_result<'py>(result: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = result.py();
    let capture: Bound<'py, PyAny> = native_field(result, "capture_result")?;
    let mut relations: Vec<Bound<'py, PyDict>> = Vec::new();
    let mut manifest_path: Bound<'py, PyAny> = py.None().into_bound(py);
    if !capture.is_none() {
        for relation in items(&native_field(&capture, "relation_results")?)? {
            relations.push(with_errors(
                &relation,
                vec![
                    ("kind", value(&relation, "kind")?),
                    ("logical_name", native_field(&relation, "logical_name")?),
                    (
                        "source_relation",
                        native_field(&relation, "source_relation")?,
                    ),
                    (
                        "file_path",
                        native_field(&relation, "file_path")?.str()?.into_any(),
                    ),
                    ("status", value(&relation, "status")?),
                    ("row_count", native_field(&relation, "row_count")?),
                    ("byte_count", native_field(&relation, "byte_count")?),
                ],
            )?);
        }
        manifest_path = native_field(&capture, "manifest_path")?.str()?.into_any();
    }
    with_errors(
        result,
        vec![
            ("name", native_field(result, "scenario_name")?),
            ("status", value(result, "status")?),
            ("retained", native_field(result, "retained")?),
            ("relations", tuple_of(py, relations)?),
            ("manifest_path", manifest_path),
        ],
    )
}
