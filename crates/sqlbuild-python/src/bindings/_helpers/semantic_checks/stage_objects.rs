//! The Python models, enums and compile helpers the semantic completion stage reads and builds.

use crate::bindings::_helpers::compiler_records::shape_classes::shape_class;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString};

const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";

const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const UNNEEDED_SQL_ANALYSIS_OPT_OUT_CODE: &str = "P009";
const SQL_ANALYSIS_CONFIG_KEY: &str = "sql_analysis";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild.spec.contracts.models";
const PROJECT_WITH_MODULE: &str = "sqlbuild._native";
const TYPE_RECOVERY_MODULE: &str = "sqlbuild._native";
const BINDING_DIAGNOSTICS_MODULE: &str = "sqlbuild._native";
const NATIVE_MODULE: &str = "sqlbuild._native";
const NORMALIZE_TYPE_MODULE: &str = "sqlbuild.adapter.type_system.main.normalize_type";
const DATACLASSES_MODULE: &str = "dataclasses";
const REFERENCE_TYPES_MODULE: &str = "sqlbuild.compiler.references.types";

/// Imported once per stage run.
pub(crate) struct StageClasses<'py> {
    pub(crate) diagnostic: Bound<'py, PyAny>,
    pub(crate) location: Bound<'py, PyAny>,
    pub(crate) model_test_payload: Bound<'py, PyAny>,
    pub(crate) compile_phase: Bound<'py, PyAny>,
    pub(crate) error: Bound<'py, PyAny>,
    pub(crate) warning: Bound<'py, PyAny>,
    pub(crate) model_resource: Bound<'py, PyAny>,
    pub(crate) source_resource: Bound<'py, PyAny>,
    pub(crate) sql_test_resource: Bound<'py, PyAny>,
    pub(crate) opt_out_code: Bound<'py, PyAny>,
    pub(crate) replace: Bound<'py, PyAny>,
    pub(crate) project_with: Bound<'py, PyAny>,
    pub(crate) with_type_recovery: Bound<'py, PyAny>,
    pub(crate) with_binding_diagnostics: Bound<'py, PyAny>,
    pub(crate) schema_validations: Bound<'py, PyAny>,
    pub(crate) normalize_type: Bound<'py, PyAny>,
    pub(crate) sql_analysis_key: Bound<'py, PyAny>,
    pub(crate) udf_kind: Bound<'py, PyAny>,
    pub(crate) table_function_kind: Bound<'py, PyAny>,
}

impl<'py> StageClasses<'py> {
    pub(crate) fn new(py: Python<'py>) -> PyResult<Self> {
        let models = py.import(COMPILE_MODELS_MODULE)?;
        let types = py.import(COMPILE_TYPES_MODULE)?;
        let severity = shape_class(types.as_any(), "DiagnosticSeverity")?;
        let resource = types.getattr("CompiledResourceType")?;
        let kinds = py
            .import(REFERENCE_TYPES_MODULE)?
            .getattr("SqlReferenceKind")?;
        Ok(Self {
            diagnostic: models.getattr("CompilerDiagnostic")?,
            location: py
                .import(CONTRACT_MODELS_MODULE)?
                .getattr("SourceLocation")?,
            model_test_payload: shape_class(models.as_any(), "CompiledModelSqlTestPayload")?,
            compile_phase: shape_class(types.as_any(), "DiagnosticPhase")?.getattr("COMPILE")?,
            error: severity.getattr("ERROR")?,
            warning: severity.getattr("WARNING")?,
            model_resource: resource.getattr("MODEL")?,
            source_resource: resource.getattr("SOURCE")?,
            sql_test_resource: resource.getattr("SQL_TEST")?,
            opt_out_code: PyString::new(py, UNNEEDED_SQL_ANALYSIS_OPT_OUT_CODE).into_any(),
            replace: py.import(DATACLASSES_MODULE)?.getattr("replace")?,
            project_with: py.import(PROJECT_WITH_MODULE)?.getattr("project_with")?,
            with_type_recovery: py
                .import(TYPE_RECOVERY_MODULE)?
                .getattr("with_type_recovery")?,
            with_binding_diagnostics: py
                .import(BINDING_DIAGNOSTICS_MODULE)?
                .getattr("with_binding_diagnostics")?,
            schema_validations: py.import(NATIVE_MODULE)?.getattr("schema_validations")?,
            normalize_type: py
                .import(NORMALIZE_TYPE_MODULE)?
                .getattr("normalize_type")?,
            sql_analysis_key: PyString::new(py, SQL_ANALYSIS_CONFIG_KEY).into_any(),
            udf_kind: kinds.getattr("UDF")?,
            table_function_kind: kinds.getattr("TABLE_FUNCTION")?,
        })
    }

    pub(crate) fn py(&self) -> Python<'py> {
        self.diagnostic.py()
    }

    /// `callable(**pairs)`.
    pub(crate) fn call(
        &self,
        callable: &Bound<'py, PyAny>,
        pairs: &[(&str, &Bound<'py, PyAny>)],
    ) -> PyResult<Bound<'py, PyAny>> {
        let kwargs: Bound<'py, PyDict> = PyDict::new(self.py());
        for (name, value) in pairs {
            kwargs.set_item(*name, *value)?;
        }
        callable.call((), Some(&kwargs))
    }

    /// `dataclasses.replace(value, **pairs)`.
    pub(crate) fn replaced(
        &self,
        value: &Bound<'py, PyAny>,
        pairs: &[(&str, &Bound<'py, PyAny>)],
    ) -> PyResult<Bound<'py, PyAny>> {
        let kwargs: Bound<'py, PyDict> = PyDict::new(self.py());
        for (name, value) in pairs {
            kwargs.set_item(*name, *value)?;
        }
        self.replace.call((value,), Some(&kwargs))
    }

    /// `project_with(project=project, **pairs)`.
    pub(crate) fn project_with(
        &self,
        project: &Bound<'py, PyAny>,
        pairs: &[(&str, &Bound<'py, PyAny>)],
    ) -> PyResult<Bound<'py, PyAny>> {
        let mut all: Vec<(&str, &Bound<'py, PyAny>)> = vec![("project", project)];
        all.extend_from_slice(pairs);
        self.call(&self.project_with, &all)
    }
}
