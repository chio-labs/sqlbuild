//! Persistent identities of compiled SQL test artifacts, so unchanged tests keep their files.

use std::collections::HashMap;
use std::path::PathBuf;

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyInt, PyList, PyListMethods, PyString, PyTuple};
use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use sqlbuild_cache::artifacts::main::stored_sql_test_record::stored_sql_test_record;
use sqlbuild_cache::artifacts::models::{SqlTestArtifactRecord, StoredSqlTestRecord};
use sqlbuild_cache::digest::main::bytes_digest::bytes_digest;
use sqlbuild_cache::digest::main::hex_digest::hex_digest;

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::compile_outputs::json_report::{compact_sorted_json, orjson_sorted};
use crate::bindings::_helpers::records::construct::record_class;
use crate::bindings::_helpers::records::ids::RecordId;

const CACHE_VERSION: i64 = 5;
const ALGORITHM_FINGERPRINT: &str = "sql-test-artifact-v5-orjson-blake3-identity";
/// Items a loop holding the interpreter handles before letting other threads run.
const INTERPRETER_YIELD_INTERVAL: usize = 64;
const CACHE_FILE_NAME: &str = "sql-test-artifacts.json";
const MAX_CACHE_BYTES: u64 = 10_000_000;
const MAX_CACHE_RECORDS: usize = 100_000;
const METADATA_MODULE: &str = "importlib.metadata";

/// The digest shared by every test artifact identity, and each model's own identity.
pub(crate) struct IdentityContext<'py> {
    common_identity: String,
    model_identities: Bound<'py, PyDict>,
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

/// `sorted(items)`, as Python orders them.
fn sorted<'py>(items: Bound<'py, PyList>) -> PyResult<Bound<'py, PyAny>> {
    items
        .py()
        .import("builtins")?
        .getattr("sorted")?
        .call1((items,))
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
    let pairs: Bound<'py, PyList> = PyList::empty(py);
    for dep in deps.try_iter()? {
        let dep: Bound<'py, PyAny> = dep?;
        pairs.append((dep.getattr("resource_type")?.str()?, dep.getattr("name")?))?;
    }
    sorted(pairs)
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
) -> PyResult<IdentityContext<'py>> {
    let py: Python<'py> = project.py();
    let adapter_type: Bound<'py, PyAny> = adapter.get_type().into_any();
    let functions: Bound<'py, PyList> = PyList::empty(py);
    for function in project.getattr("functions")?.try_iter()? {
        let function: Bound<'py, PyAny> = function?;
        functions.append((
            function.getattr("name")?,
            function.getattr("destination")?.getattr("qualified_name")?,
        ))?;
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
            ("function_locations", sorted(functions)?),
        ],
    )?;
    let mut names: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut payloads: Vec<String> = Vec::new();
    for (index, model) in project.getattr("models")?.try_iter()?.enumerate() {
        let model: Bound<'py, PyAny> = model?;
        names.push(model.getattr("name")?);
        payloads.push(model_identity_payload(&model)?);
        yield_interpreter(py, index);
    }
    payloads.push(payload_text(common.as_any())?);
    let mut digests: Vec<String> = payload_digests(py, &payloads);
    let common_identity: String = digests.pop().unwrap_or_default();
    let model_identities: Bound<'py, PyDict> = PyDict::new(py);
    for (name, digest) in names.into_iter().zip(digests) {
        model_identities.set_item(name, digest)?;
    }
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
    sorted(PyList::new(
        py,
        mapping
            .call_method0("items")?
            .try_iter()?
            .collect::<PyResult<Vec<_>>>()?,
    )?)
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
    context: &IdentityContext<'_>,
) -> PyResult<String> {
    let py: Python<'_> = test.py();
    let chain: Bound<'_, PyList> = PyList::empty(py);
    for name in model_chain_names.try_iter()? {
        let name: Bound<'_, PyAny> = name?;
        let identity: Option<Bound<'_, PyAny>> = context.model_identities.get_item(&name)?;
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

/// A string field of a stored record, or `None` when absent or not a string.
fn stored_text(fields: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    match fields.get_item(key)? {
        Some(item) if item.is_instance_of::<PyString>() => Ok(Some(item.extract()?)),
        _ => Ok(None),
    }
}

/// A non-negative integer field of a stored record, or `None` when absent, negative or not an `int`.
fn stored_integer(fields: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<u64>> {
    let Some(item) = fields.get_item(key)? else {
        return Ok(None);
    };
    if !item.is_instance_of::<PyInt>() || item.is_instance_of::<PyBool>() {
        return Ok(None);
    }
    let Ok(number) = item.extract::<u64>() else {
        return Ok(None);
    };
    Ok(Some(number))
}

/// One stored record, or `None` when any field has the wrong type or an unsafe path.
fn stored_record(value: &Bound<'_, PyAny>) -> PyResult<Option<SqlTestArtifactRecord>> {
    let Ok(fields) = value.downcast::<PyDict>() else {
        return Ok(None);
    };
    let (Some(identity), Some(relative_path), Some(content_sha256)) = (
        stored_text(fields, "identity")?,
        stored_text(fields, "relative_path")?,
        stored_text(fields, "content_sha256")?,
    ) else {
        return Ok(None);
    };
    let (Some(size), Some(mtime_ns)) = (
        stored_integer(fields, "size")?,
        stored_integer(fields, "mtime_ns")?,
    ) else {
        return Ok(None);
    };
    let Ok(mtime_ns) = i64::try_from(mtime_ns) else {
        return Ok(None);
    };
    Ok(stored_sql_test_record(StoredSqlTestRecord {
        identity,
        relative_path,
        size,
        mtime_ns,
        content_sha256,
    }))
}

/// The valid cache records; a cache that cannot be read never fails compilation.
pub(crate) fn read_cache(
    cache_dir: &Bound<'_, PyAny>,
) -> PyResult<HashMap<String, SqlTestArtifactRecord>> {
    let py: Python<'_> = cache_dir.py();
    if cache_dir.is_none() {
        return Ok(HashMap::new());
    }
    let cache_path: PathBuf = cache_dir.extract::<PathBuf>()?.join(CACHE_FILE_NAME);
    let Ok(metadata) = std::fs::metadata(&cache_path) else {
        return Ok(HashMap::new());
    };
    if !metadata.is_file() || metadata.len() > MAX_CACHE_BYTES {
        return Ok(HashMap::new());
    }
    let Ok(contents) = std::fs::read(&cache_path) else {
        return Ok(HashMap::new());
    };
    let Ok(text) = String::from_utf8(contents) else {
        return Ok(HashMap::new());
    };
    let payload: Bound<'_, PyAny> = match imported(py, "json", "loads")?.call1((text,)) {
        Ok(payload) => payload,
        Err(error) if error.is_instance_of::<pyo3::exceptions::PyValueError>(py) => {
            return Ok(HashMap::new());
        }
        Err(error) => return Err(error),
    };
    let Ok(payload) = payload.downcast::<PyDict>() else {
        return Ok(HashMap::new());
    };
    let version: Option<Bound<'_, PyAny>> = payload.get_item("version")?;
    if !version.is_some_and(|version| version.eq(CACHE_VERSION).unwrap_or(false)) {
        return Ok(HashMap::new());
    }
    let Some(raw_records) = payload.get_item("records")? else {
        return Ok(HashMap::new());
    };
    let Ok(raw_records) = raw_records.downcast::<PyDict>() else {
        return Ok(HashMap::new());
    };
    if raw_records.len() > MAX_CACHE_RECORDS {
        return Ok(HashMap::new());
    }
    let mut records: HashMap<String, SqlTestArtifactRecord> = HashMap::new();
    for (key, value) in raw_records.iter() {
        if let Some(record) = stored_record(&value)? {
            records.insert(key.extract()?, record);
        }
    }
    Ok(records)
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
    let rows: Bound<'_, PyDict> = PyDict::new(py);
    for (key, record) in records {
        rows.set_item(
            key,
            dict(
                py,
                vec![
                    ("identity", record.identity.as_str().into_bound_py_any(py)?),
                    (
                        "relative_path",
                        record.relative_posix().into_bound_py_any(py)?,
                    ),
                    ("size", record.size.into_bound_py_any(py)?),
                    ("mtime_ns", record.mtime_ns.into_bound_py_any(py)?),
                    (
                        "content_sha256",
                        record.content_sha256.as_str().into_bound_py_any(py)?,
                    ),
                ],
            )?,
        )?;
    }
    let payload: Bound<'_, PyDict> = dict(
        py,
        vec![
            ("version", CACHE_VERSION.into_bound_py_any(py)?),
            ("records", rows.into_any()),
        ],
    )?;
    let encoded: String = compact_sorted_json(payload.as_any())?;
    let directory: PathBuf = cache_dir.extract()?;
    let temporary: PathBuf =
        directory.join(format!(".{CACHE_FILE_NAME}.{}.tmp", std::process::id()));
    let written: std::io::Result<()> = py.detach(|| {
        std::fs::create_dir_all(&directory)?;
        std::fs::write(&temporary, encoded.as_bytes())?;
        std::fs::rename(&temporary, directory.join(CACHE_FILE_NAME))
    });
    let _ = written;
    Ok(())
}
