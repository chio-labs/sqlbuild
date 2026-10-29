//! Persistent identities of compiled SQL test artifacts, so unchanged tests keep their files.

use std::collections::HashMap;
use std::path::PathBuf;

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyListMethods, PyTuple};
use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use sqlbuild_cache::artifacts::main::read_sql_test_cache::read_sql_test_cache;
use sqlbuild_cache::artifacts::main::write_sql_test_cache::write_sql_test_cache;
use sqlbuild_cache::artifacts::models::SqlTestArtifactRecord;
use sqlbuild_cache::digest::main::bytes_digest::bytes_digest;
use sqlbuild_cache::digest::main::hex_digest::hex_digest;

use crate::bindings::_helpers::boundary::python_calls::imported;
use crate::bindings::_helpers::compile_outputs::json_report::orjson_sorted;
use crate::bindings::_helpers::records::construct::record_class;
use crate::bindings::_helpers::records::ids::RecordId;

const ALGORITHM_FINGERPRINT: &str = "sql-test-artifact-v5-orjson-blake3-identity";
/// Items a loop holding the interpreter handles before letting other threads run.
const INTERPRETER_YIELD_INTERVAL: usize = 64;
const METADATA_MODULE: &str = "importlib.metadata";

/// The digest shared by every test artifact identity, and each model's own identity.
pub(crate) struct IdentityContext {
    common_identity: String,
    model_identities: HashMap<String, String>,
}

/// `orjson.dumps(payload, option=OPT_SORT_KEYS)`, the text an identity digest is taken of.
fn payload_text(payload: &Bound<'_, PyAny>) -> PyResult<String> {
    orjson_sorted(payload)
}

/// The hexadecimal BLAKE3 digest of each payload text, hashed without holding the interpreter.
pub(crate) fn payload_digests(py: Python<'_>, payloads: &[String]) -> Vec<String> {
    py.detach(|| {
        payloads
            .par_iter()
            .map(|payload| hex_digest(&bytes_digest(payload.as_bytes())))
            .collect()
    })
}

/// Let other threads take the interpreter every few items of a long loop that holds it.
pub(crate) fn yield_interpreter(py: Python<'_>, index: usize) {
    if index % INTERPRETER_YIELD_INTERVAL == INTERPRETER_YIELD_INTERVAL - 1 {
        py.detach(|| ());
    }
}

fn dict<'py>(
    py: Python<'py>,
    entries: Vec<(&str, Bound<'py, PyAny>)>,
) -> PyResult<Bound<'py, PyDict>> {
    let built: Bound<'py, PyDict> = PyDict::new(py);
    for (key, value) in entries {
        built.set_item(key, value)?;
    }
    Ok(built)
}

/// String pairs ordered lexicographically, as Python orders these cache inputs.
fn sorted_pairs(py: Python<'_>, mut items: Vec<(String, String)>) -> PyResult<Bound<'_, PyAny>> {
    items.sort();
    Ok(PyList::new(py, items)?.into_any())
}

fn package_version<'py>(py: Python<'py>, package: &str) -> PyResult<Bound<'py, PyAny>> {
    match imported(py, METADATA_MODULE, "version")?.call1((package,)) {
        Ok(version) => Ok(version),
        Err(error)
            if error.is_instance(py, &imported(py, METADATA_MODULE, "PackageNotFoundError")?) =>
        {
            "unknown".into_bound_py_any(py)
        }
        Err(error) => Err(error),
    }
}

/// `sorted((str(dep.resource_type), dep.name) for dep in deps)`.
fn sorted_deps<'py>(deps: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = deps.py();
    let mut pairs: Vec<(String, String)> = Vec::new();
    for dep in deps.try_iter()? {
        let dep: Bound<'py, PyAny> = dep?;
        pairs.push((
            dep.getattr("resource_type")?.str()?.extract()?,
            dep.getattr("name")?.extract()?,
        ));
    }
    sorted_pairs(py, pairs)
}

fn model_identity_payload(model: &Bound<'_, PyAny>) -> PyResult<String> {
    let py: Python<'_> = model.py();
    let values: Bound<'_, PyAny> = model.getattr("config")?.getattr("values")?;
    payload_text(
        dict(
            py,
            vec![
                ("name", model.getattr("name")?),
                ("query_sql", model.getattr("query_sql")?),
                ("deps", sorted_deps(&model.getattr("deps")?)?),
                (
                    "cursor",
                    (
                        values.call_method1("get", ("cursor_type",))?,
                        values.call_method1("get", ("cursor_grain",))?,
                    )
                        .into_bound_py_any(py)?,
                ),
            ],
        )?
        .as_any(),
    )
}

/// Hash adapter and model inputs once for every test artifact identity.
pub(crate) fn identity_context<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
) -> PyResult<IdentityContext> {
    let py: Python<'py> = project.py();
    let adapter_type: Bound<'py, PyAny> = adapter.get_type().into_any();
    let mut functions: Vec<(String, String)> = Vec::new();
    for function in project.getattr("functions")?.try_iter()? {
        let function: Bound<'py, PyAny> = function?;
        functions.push((
            function.getattr("name")?.extract()?,
            function
                .getattr("destination")?
                .getattr("qualified_name")?
                .extract()?,
        ));
    }
    let version_tuple: Bound<'py, PyAny> = py
        .import("platform")?
        .call_method0("python_version_tuple")?
        .get_item(pyo3::types::PySlice::new(py, 0, 2, 1))?;
    let common: Bound<'py, PyDict> = dict(
        py,
        vec![
            ("algorithm", ALGORITHM_FINGERPRINT.into_bound_py_any(py)?),
            ("sqlbuild_version", package_version(py, "sqlbuild")?),
            (
                "polyglot_version",
                package_version(py, "polyglot-sql-chio")?,
            ),
            ("python_version", version_tuple),
            (
                "adapter_class",
                format!(
                    "{}.{}",
                    adapter_type.getattr("__module__")?.str()?,
                    adapter_type.getattr("__qualname__")?.str()?
                )
                .into_bound_py_any(py)?,
            ),
            (
                "set_difference_operator",
                adapter.call_method0("render_set_difference_operator")?,
            ),
            (
                "sql_analysis_dialect",
                adapter.call_method0("sql_analysis_dialect")?,
            ),
            (
                "requires_derived_table_aliases",
                adapter.call_method0("requires_derived_table_aliases")?,
            ),
            (
                "sql_analysis_enabled",
                project.getattr("settings")?.getattr("sql_analysis")?,
            ),
            (
                "effective_target_name",
                project.getattr("effective_target_name")?,
            ),
            (
                "effective_target_database",
                project.getattr("effective_target_database")?,
            ),
            (
                "effective_target_schema",
                project.getattr("effective_target_schema")?,
            ),
            ("function_locations", sorted_pairs(py, functions)?),
        ],
    )?;
    let mut names: Vec<String> = Vec::new();
    let mut payloads: Vec<String> = Vec::new();
    for (index, model) in project.getattr("models")?.try_iter()?.enumerate() {
        let model: Bound<'py, PyAny> = model?;
        names.push(model.getattr("name")?.extract()?);
        payloads.push(model_identity_payload(&model)?);
        yield_interpreter(py, index);
    }
    payloads.push(payload_text(common.as_any())?);
    let mut digests: Vec<String> = payload_digests(py, &payloads);
    let common_identity: String = digests.pop().unwrap_or_default();
    let model_identities: HashMap<String, String> = names.into_iter().zip(digests).collect();
    Ok(IdentityContext {
        common_identity,
        model_identities,
    })
}

/// `[(cte.name, cte.sql_body) for cte in ctes]`.
fn cte_payload<'py>(ctes: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = ctes.py();
    let rows: Bound<'py, PyList> = PyList::empty(py);
    for cte in ctes.try_iter()? {
        let cte: Bound<'py, PyAny> = cte?;
        rows.append((cte.getattr("name")?, cte.getattr("sql_body")?))?;
    }
    Ok(rows.into_any())
}

/// `sorted(mapping.items())`.
fn sorted_items<'py>(mapping: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = mapping.py();
    sorted_pairs(
        py,
        mapping
            .call_method0("items")?
            .try_iter()?
            .map(|item| item?.extract::<(String, String)>())
            .collect::<PyResult<Vec<_>>>()?,
    )
}

fn test_payload<'py>(test: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = test.py();
    let payload: Bound<'py, PyDict> = dict(
        py,
        vec![
            ("case_fingerprint", test.getattr("case_fingerprint")?),
            ("mode", test.getattr("mode")?.getattr("value")?),
            ("sql_body", test.getattr("sql_body")?),
            ("scope_deps", sorted_deps(&test.getattr("scope_deps")?)?),
        ],
    )?;
    let test_payload: Bound<'py, PyAny> = test.getattr("payload")?;
    if test_payload.is_instance(&record_class(py, RecordId::CompiledModelSqlTestPayload)?)? {
        let block: Bound<'py, PyAny> = test.getattr("test_block")?;
        payload.set_item(
            "model",
            dict(
                py,
                vec![
                    (
                        "authored_ctes",
                        cte_payload(&test_payload.getattr("authored_ctes")?)?,
                    ),
                    (
                        "macro_mocks",
                        sorted_items(&test_payload.getattr("macro_mocks")?)?,
                    ),
                    (
                        "model_query_overrides",
                        sorted_items(&test_payload.getattr("model_query_overrides")?)?,
                    ),
                    (
                        "expected_model_names",
                        test_payload.getattr("expected_model_names")?,
                    ),
                    (
                        "assertion_ctes",
                        cte_payload(&test_payload.getattr("assertion_ctes")?)?,
                    ),
                    (
                        "cursor_window",
                        (block.getattr("cursor_start")?, block.getattr("cursor_end")?)
                            .into_bound_py_any(py)?,
                    ),
                ],
            )?,
        )?;
    } else if test_payload.is_instance(&record_class(
        py,
        RecordId::CompiledDirectLogicSqlTestPayload,
    )?)? {
        payload.set_item(
            "direct",
            dict(
                py,
                vec![
                    (
                        "helper_ctes",
                        cte_payload(&test_payload.getattr("helper_ctes")?)?,
                    ),
                    (
                        "actual_cte",
                        cte_payload(
                            PyTuple::new(py, [test_payload.getattr("actual_cte")?])?.as_any(),
                        )?,
                    ),
                    (
                        "expected_cte",
                        cte_payload(
                            PyTuple::new(py, [test_payload.getattr("expected_cte")?])?.as_any(),
                        )?,
                    ),
                    (
                        "tested_resource_names",
                        test_payload.getattr("tested_resource_names")?,
                    ),
                ],
            )?,
        )?;
    }
    Ok(payload)
}

/// The text whose digest is the complete identity of one rendered comparison artifact.
pub(crate) fn artifact_identity_payload(
    test: &Bound<'_, PyAny>,
    model_chain_names: &Bound<'_, PyAny>,
    context: &IdentityContext,
) -> PyResult<String> {
    let py: Python<'_> = test.py();
    let chain: Bound<'_, PyList> = PyList::empty(py);
    for name in model_chain_names.try_iter()? {
        let name: String = name?.extract()?;
        let identity: Option<&String> = context.model_identities.get(&name);
        chain.append((name, identity))?;
    }
    payload_text(
        dict(
            py,
            vec![
                (
                    "common_identity",
                    context.common_identity.as_str().into_bound_py_any(py)?,
                ),
                ("test", test_payload(test)?.into_any()),
                ("model_chain", chain.into_any()),
            ],
        )?
        .as_any(),
    )
}

/// The text whose digest is the stable cache slot of one source test case.
pub(crate) fn artifact_record_key_payload(test: &Bound<'_, PyAny>) -> PyResult<String> {
    let py: Python<'_> = test.py();
    let source_path: Bound<'_, PyAny> = test.getattr("source_path")?;
    payload_text(
        dict(
            py,
            vec![
                (
                    "source_path",
                    if source_path.is_none() {
                        source_path
                    } else {
                        source_path.call_method0("as_posix")?
                    },
                ),
                ("block_index", test.getattr("block_index")?),
                ("name", test.getattr("name")?),
                ("parent_name", test.getattr("parent_name")?),
                ("case_name", test.getattr("case_name")?),
                ("case_index", test.getattr("case_index")?),
            ],
        )?
        .as_any(),
    )
}

/// The valid cache records; a cache that cannot be read never fails compilation.
pub(crate) fn read_cache(
    cache_dir: &Bound<'_, PyAny>,
) -> PyResult<HashMap<String, SqlTestArtifactRecord>> {
    let py: Python<'_> = cache_dir.py();
    if cache_dir.is_none() {
        return Ok(HashMap::new());
    }
    let directory: PathBuf = cache_dir.extract()?;
    Ok(py.detach(|| read_sql_test_cache(&directory)))
}

/// Atomically replace the cache snapshot; a cache that cannot be written is ignored.
pub(crate) fn write_cache(
    cache_dir: &Bound<'_, PyAny>,
    records: &[(String, SqlTestArtifactRecord)],
) -> PyResult<()> {
    let py: Python<'_> = cache_dir.py();
    if cache_dir.is_none() {
        return Ok(());
    }
    let directory: PathBuf = cache_dir.extract()?;
    py.detach(|| write_sql_test_cache(&directory, records));
    Ok(())
}
