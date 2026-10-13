//! Compiled SQL tests, their keyed P013 diagnostics and assembly failures, built natively.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::sql_test_glue::assembly::{
    AssemblyRequest, AssemblyRow, DiagnosticRow, FactsRow, assemble_compiled_sql_tests,
};

const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const COMPILE_CONSTANTS_MODULE: &str = "sqlbuild.compiler.compile.constants";
const GLUE_MODELS_MODULE: &str = "sqlbuild.compiler.sql_test_glue.models";
const SPEC_MODELS_MODULE: &str = "sqlbuild.spec.contracts.models";
/// Fields a direct-logic compiled payload copies from its input payload, in order.
const DIRECT_PAYLOAD_FIELDS: [&str; 5] = [
    "mode",
    "helper_ctes",
    "actual_cte",
    "expected_cte",
    "tested_resource_names",
];
/// Fields a model compiled payload copies from its input payload, in order.
const MODEL_PAYLOAD_FIELDS: [&str; 11] = [
    "authored_ctes",
    "macro_mocks",
    "mock_model_names",
    "mock_source_names",
    "mock_seed_names",
    "mock_dbt_ref_names",
    "mock_table_function_names",
    "expected_ctes",
    "expected_model_names",
    "assertion_ctes",
    "assertion_names",
];
/// Model payload name lists a compiled test also records on itself.
const MODEL_TEST_FIELDS: [&str; 5] = [
    "expected_model_names",
    "assertion_names",
    "assertion_target_model_names",
    "read_helper_names",
    "reference_target_model_names",
];

/// Keyword arguments of one Python constructor call, in order.
type Fields<'py> = Vec<(&'static str, Bound<'py, PyAny>)>;

/// The Python classes a compiled test is built from.
struct Classes<'py> {
    models: Bound<'py, PyModule>,
    resource_type: Bound<'py, PyAny>,
    direct_input: Bound<'py, PyAny>,
    assembly: Bound<'py, PyAny>,
    failure: Bound<'py, PyAny>,
    location: Bound<'py, PyAny>,
    phase: Bound<'py, PyAny>,
    severity: Bound<'py, PyAny>,
    code: Bound<'py, PyAny>,
}

impl<'py> Classes<'py> {
    fn new(py: Python<'py>) -> PyResult<Self> {
        let models: Bound<'py, PyModule> = py.import(COMPILE_MODELS_MODULE)?;
        let types: Bound<'py, PyModule> = py.import(COMPILE_TYPES_MODULE)?;
        let glue: Bound<'py, PyModule> = py.import(GLUE_MODELS_MODULE)?;
        Ok(Self {
            direct_input: models.getattr("CompileDirectLogicSqlTestInputPayload")?,
            resource_type: types.getattr("CompiledResourceType")?,
            phase: types.getattr("DiagnosticPhase")?.getattr("COMPILE")?,
            severity: types.getattr("DiagnosticSeverity")?.getattr("ERROR")?,
            assembly: glue.getattr("NativeSqlTestAssembly")?,
            failure: glue.getattr("NativeSqlTestFailure")?,
            location: py.import(SPEC_MODELS_MODULE)?.getattr("SourceLocation")?,
            code: py
                .import(COMPILE_CONSTANTS_MODULE)?
                .getattr("SQL_TEST_HELPER_REFERENCE_CODE")?,
            models,
        })
    }

    fn py(&self) -> Python<'py> {
        self.models.py()
    }

    fn model(&self, name: &str) -> PyResult<Bound<'py, PyAny>> {
        self.models.getattr(name)
    }

    fn object_key(&self, resource_type: &str, name: &str) -> PyResult<Bound<'py, PyAny>> {
        keyword_call(
            &self.model("CompiledObjectKey")?,
            vec![
                ("resource_type", self.resource_type.call1((resource_type,))?),
                ("name", text(self.py(), name)),
            ],
        )
    }
}

fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

fn keyword_call<'py>(
    callable: &Bound<'py, PyAny>,
    pairs: Vec<(&str, Bound<'py, PyAny>)>,
) -> PyResult<Bound<'py, PyAny>> {
    let keywords: Bound<'py, PyDict> = PyDict::new(callable.py());
    for (name, value) in pairs {
        keywords.set_item(name, value)?;
    }
    callable.call((), Some(&keywords))
}

fn copied<'py>(
    source: &Bound<'py, PyAny>,
    fields: &[&'static str],
) -> PyResult<Vec<(&'static str, Bound<'py, PyAny>)>> {
    fields
        .iter()
        .map(|field| Ok((*field, source.getattr(*field)?)))
        .collect()
}

/// The compiled payload, tested resources and recorded model names of one test input.
fn compiled_payload<'py>(
    classes: &Classes<'py>,
    payload: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Fields<'py>)> {
    let py: Python<'py> = classes.py();
    if payload.is_instance(&classes.direct_input)? {
        let compiled: Bound<'py, PyAny> = keyword_call(
            &classes.model("CompiledDirectLogicSqlTestPayload")?,
            copied(payload, &DIRECT_PAYLOAD_FIELDS)?,
        )?;
        let resource_type: Bound<'py, PyAny> = classes.model("CompiledSqlTestResource")?;
        let mode: Bound<'py, PyAny> = payload.getattr("mode")?;
        let mut resources: Vec<Bound<'py, PyAny>> = Vec::new();
        for name in payload.getattr("tested_resource_names")?.try_iter()? {
            resources.push(keyword_call(
                &resource_type,
                vec![("kind", mode.clone()), ("name", name?)],
            )?);
        }
        let mut fields: Vec<(&'static str, Bound<'py, PyAny>)> = MODEL_TEST_FIELDS
            .iter()
            .map(|field| (*field, PyTuple::empty(py).into_any()))
            .collect();
        fields.push(("tested_resources", PyTuple::new(py, resources)?.into_any()));
        return Ok((compiled, fields));
    }
    let mut payload_fields: Vec<(&'static str, Bound<'py, PyAny>)> =
        copied(payload, &MODEL_PAYLOAD_FIELDS)?;
    payload_fields.push(("model_query_overrides", PyDict::new(py).into_any()));
    let compiled: Bound<'py, PyAny> = keyword_call(
        &classes.model("CompiledModelSqlTestPayload")?,
        payload_fields,
    )?;
    let mut fields: Vec<(&'static str, Bound<'py, PyAny>)> = copied(payload, &MODEL_TEST_FIELDS)?;
    fields.push(("tested_resources", PyTuple::empty(py).into_any()));
    Ok((compiled, fields))
}

/// One P013 diagnostic and the key compile reports it under.
fn keyed_diagnostic<'py>(
    classes: &Classes<'py>,
    (test_input, resource_name): (&Bound<'py, PyAny>, &str),
    (line, column, end_line, end_column, message, help): DiagnosticRow,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = classes.py();
    let path: Bound<'py, PyAny> = test_input.getattr("test_file")?.getattr("relative_path")?;
    let key: Bound<'py, PyTuple> = PyTuple::new(
        py,
        [
            classes.code.clone(),
            path.call_method0("as_posix")?,
            text(py, &format!("{line:09}:{column:09}")),
            text(py, &message),
        ],
    )?;
    let location: Bound<'py, PyAny> = keyword_call(
        &classes.location,
        vec![
            ("path", path),
            ("line", line.into_pyobject(py)?.into_any()),
            ("column", column.into_pyobject(py)?.into_any()),
            ("end_line", end_line.into_pyobject(py)?.into_any()),
            ("end_column", end_column.into_pyobject(py)?.into_any()),
        ],
    )?;
    let diagnostic: Bound<'py, PyAny> = keyword_call(
        &classes.model("CompilerDiagnostic")?,
        vec![
            ("phase", classes.phase.clone()),
            ("severity", classes.severity.clone()),
            ("code", classes.code.clone()),
            ("message", text(py, &message)),
            ("resource_type", classes.resource_type.call1(("sql_test",))?),
            ("resource_name", text(py, resource_name)),
            ("location", location),
            ("help", text(py, &help)),
        ],
    )?;
    PyTuple::new(py, [key.into_any(), diagnostic])
}

/// The compiled test and keyed diagnostics one input's assembled facts describe.
fn compiled_test<'py>(
    classes: &Classes<'py>,
    test_input: &Bound<'py, PyAny>,
    facts: FactsRow,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyTuple>)> {
    let py: Python<'py> = classes.py();
    let (name, scope_rows, target_model_names, case_fingerprint, resource_name, diagnostics) =
        facts;
    let scope_deps: Vec<Bound<'py, PyAny>> = scope_rows
        .iter()
        .map(|(resource_type, dep)| classes.object_key(resource_type, dep))
        .collect::<PyResult<_>>()?;
    let (payload, payload_fields) = compiled_payload(classes, &test_input.getattr("payload")?)?;
    let test_file: Bound<'py, PyAny> = test_input.getattr("test_file")?;
    let test_block: Bound<'py, PyAny> = test_input.getattr("test_block")?;
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = vec![
        ("key", classes.object_key("sql_test", &name)?),
        ("scope_deps", PyTuple::new(py, scope_deps)?.into_any()),
        ("name", text(py, &name)),
        ("test_file", test_file.clone()),
        ("test_block", test_block.clone()),
        ("sql_body", test_input.getattr("sql_body")?),
        ("mode", test_input.getattr("mode")?),
        ("payload", payload),
        ("source_path", test_file.getattr("relative_path")?),
        ("ownership_root", test_file.getattr("ownership_root")?),
        ("block_index", test_block.getattr("test_index")?),
        ("explicit_name", test_block.getattr("name")?),
        ("parent_name", test_input.getattr("parent_name")?),
        ("case_name", test_input.getattr("case_name")?),
        ("case_index", test_input.getattr("case_index")?),
        (
            "case_fingerprint",
            case_fingerprint.into_pyobject(py)?.into_any(),
        ),
        ("parameter_schema", test_input.getattr("parameter_schema")?),
        ("parameter_values", test_input.getattr("parameter_values")?),
        (
            "target_model_names",
            PyTuple::new(py, target_model_names)?.into_any(),
        ),
    ];
    fields.extend(payload_fields);
    let test: Bound<'py, PyAny> = keyword_call(&classes.model("CompiledSqlTest")?, fields)?;
    let keyed: Vec<Bound<'py, PyTuple>> = diagnostics
        .into_iter()
        .map(|row| keyed_diagnostic(classes, (test_input, &resource_name), row))
        .collect::<PyResult<_>>()?;
    Ok((test, PyTuple::new(py, keyed)?))
}

fn assembly<'py>(
    classes: &Classes<'py>,
    test_input: &Bound<'py, PyAny>,
    (facts, failure): AssemblyRow,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = classes.py();
    let failure: Bound<'py, PyAny> = match failure {
        Some((kind, message)) => keyword_call(
            &classes.failure,
            vec![("kind", text(py, kind)), ("message", text(py, &message))],
        )?,
        None => py.None().into_bound(py),
    };
    let (test, diagnostics): (Bound<'py, PyAny>, Bound<'py, PyTuple>) = match facts {
        Some(facts) => compiled_test(classes, test_input, facts)?,
        None => (py.None().into_bound(py), PyTuple::empty(py)),
    };
    keyword_call(
        &classes.assembly,
        vec![
            ("test", test),
            ("diagnostics", diagnostics.into_any()),
            ("failure", failure),
        ],
    )
}

/// One assembly per test input, with the error its assembly raises, if any.
#[pyfunction]
#[pyo3(signature = (*, inputs))]
fn assemble_native_sql_tests<'py>(
    py: Python<'py>,
    inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let test_inputs: Vec<Bound<'py, PyAny>> = inputs.getattr("test_inputs")?.extract()?;
    let request = AssemblyRequest {
        model_inputs: inputs.getattr("model_inputs")?.extract()?,
        test_inputs: test_inputs.clone(),
        lexical_syntax: inputs
            .getattr("sql_lexical_syntax")?
            .getattr("native_mapping")?
            .extract()?,
    };
    let rows: Vec<AssemblyRow> = assemble_compiled_sql_tests(py, request)?;
    if rows.len() != test_inputs.len() {
        return Err(compiler_error(
            "native SQL test assembly returned an invalid batch response",
        ));
    }
    let classes: Classes<'py> = Classes::new(py)?;
    let assemblies: Vec<Bound<'py, PyAny>> = test_inputs
        .iter()
        .zip(rows)
        .map(|(test_input, row)| assembly(&classes, test_input, row))
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, assemblies)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(assemble_native_sql_tests, module)?)?;
    Ok(())
}
