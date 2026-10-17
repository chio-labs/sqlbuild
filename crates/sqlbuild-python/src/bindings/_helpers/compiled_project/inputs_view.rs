//! A compile's attached inputs, read from the native compiled project that owns its models.

use pyo3::exceptions::PyTypeError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{pyclass, pymethods};

use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;

const MODEL_INPUTS_FIELD: &str = "model_inputs";
const RUN_ID_FIELD: &str = "run_id";
const NO_SQL_VALIDATION_FIELD: &str = "no_sql_validation";

/// Compile inputs held as Python objects: user code, discovery or an integration owns them.
struct BoundaryInputs {
    /// The discovered project config.
    project_config: Py<PyAny>,
    /// The discovered local config.
    local_config: Py<PyAny>,
    /// The discovered project inputs.
    discovered_inputs: Py<PyAny>,
    /// The adapter's lexical syntax.
    sql_lexical_syntax: Py<PyAny>,
    /// The selected target config, or `None`.
    effective_target: Py<PyAny>,
    /// The compile cache directory path.
    compile_cache_dir: Py<PyAny>,
    /// The resolved connection, adapter integration values.
    effective_connection: Py<PyAny>,
    /// Project variables, user values.
    effective_vars: Py<PyAny>,
    /// The macro context user macro bodies run with.
    macro_context: Py<PyAny>,
    /// Loaded macro modules, user code.
    loaded_macros: Py<PyAny>,
    /// Public enums, user declaration values.
    public_enums: Py<PyAny>,
    /// Public constants, user declaration values.
    public_constants: Py<PyAny>,
    /// The external reference resolver integration, or `None`.
    external_sql_reference_resolver: Py<PyAny>,
}

/// Compiler-derived inputs still held as Python objects until they are owner facts.
struct CompilerHandles {
    /// Effective settings.
    effective_settings: Py<PyAny>,
    /// Attached seed inputs.
    seed_inputs: Py<PyAny>,
    /// Attached source inputs.
    source_inputs: Py<PyAny>,
    /// Attached SQL function inputs.
    sql_function_inputs: Py<PyAny>,
    /// Attached SQL test inputs.
    test_inputs: Py<PyAny>,
    /// Attached SQL scenario inputs.
    scenario_inputs: Py<PyAny>,
    /// Attached audit inputs.
    audit_inputs: Py<PyAny>,
    /// Compiler diagnostics.
    diagnostics: Py<PyAny>,
    /// The declaration scope index.
    scope_index: Py<PyAny>,
    /// The declaration scope build.
    declaration_scope: Py<PyAny>,
}

/// The values of one compile inputs view.
struct InputsFields {
    run_id: String,
    effective_target_name: Option<String>,
    no_sql_validation: bool,
    model_inputs: Py<PyTuple>,
    boundary: BoundaryInputs,
    compiler: CompilerHandles,
}

impl InputsFields {
    /// The fields named in `fields`, each required.
    fn from_fields(fields: &Bound<'_, PyDict>) -> PyResult<Self> {
        Ok(Self {
            run_id: required(fields, RUN_ID_FIELD)?.extract()?,
            effective_target_name: required(fields, "effective_target_name")?.extract()?,
            no_sql_validation: required(fields, NO_SQL_VALIDATION_FIELD)?.extract()?,
            model_inputs: required(fields, MODEL_INPUTS_FIELD)?
                .downcast_into::<PyTuple>()?
                .unbind(),
            boundary: BoundaryInputs {
                project_config: required(fields, "project_config")?.unbind(),
                local_config: required(fields, "local_config")?.unbind(),
                discovered_inputs: required(fields, "discovered_inputs")?.unbind(),
                sql_lexical_syntax: required(fields, "sql_lexical_syntax")?.unbind(),
                effective_target: required(fields, "effective_target")?.unbind(),
                compile_cache_dir: required(fields, "compile_cache_dir")?.unbind(),
                effective_connection: required(fields, "effective_connection")?.unbind(),
                effective_vars: required(fields, "effective_vars")?.unbind(),
                macro_context: required(fields, "macro_context")?.unbind(),
                loaded_macros: required(fields, "loaded_macros")?.unbind(),
                public_enums: required(fields, "public_enums")?.unbind(),
                public_constants: required(fields, "public_constants")?.unbind(),
                external_sql_reference_resolver: required(
                    fields,
                    "external_sql_reference_resolver",
                )?
                .unbind(),
            },
            compiler: CompilerHandles {
                effective_settings: required(fields, "effective_settings")?.unbind(),
                seed_inputs: required(fields, "seed_inputs")?.unbind(),
                source_inputs: required(fields, "source_inputs")?.unbind(),
                sql_function_inputs: required(fields, "sql_function_inputs")?.unbind(),
                test_inputs: required(fields, "test_inputs")?.unbind(),
                scenario_inputs: required(fields, "scenario_inputs")?.unbind(),
                audit_inputs: required(fields, "audit_inputs")?.unbind(),
                diagnostics: required(fields, "diagnostics")?.unbind(),
                scope_index: required(fields, "scope_index")?.unbind(),
                declaration_scope: required(fields, "declaration_scope")?.unbind(),
            },
        })
    }

    /// Every field by name.
    fn as_fields<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        fields.set_item(RUN_ID_FIELD, &self.run_id)?;
        fields.set_item("effective_target_name", &self.effective_target_name)?;
        fields.set_item(NO_SQL_VALIDATION_FIELD, self.no_sql_validation)?;
        fields.set_item(MODEL_INPUTS_FIELD, self.model_inputs.bind(py))?;
        fields.set_item("project_config", self.boundary.project_config.bind(py))?;
        fields.set_item("local_config", self.boundary.local_config.bind(py))?;
        fields.set_item(
            "discovered_inputs",
            self.boundary.discovered_inputs.bind(py),
        )?;
        fields.set_item(
            "sql_lexical_syntax",
            self.boundary.sql_lexical_syntax.bind(py),
        )?;
        fields.set_item("effective_target", self.boundary.effective_target.bind(py))?;
        fields.set_item(
            "compile_cache_dir",
            self.boundary.compile_cache_dir.bind(py),
        )?;
        fields.set_item(
            "effective_connection",
            self.boundary.effective_connection.bind(py),
        )?;
        fields.set_item("effective_vars", self.boundary.effective_vars.bind(py))?;
        fields.set_item("macro_context", self.boundary.macro_context.bind(py))?;
        fields.set_item("loaded_macros", self.boundary.loaded_macros.bind(py))?;
        fields.set_item("public_enums", self.boundary.public_enums.bind(py))?;
        fields.set_item("public_constants", self.boundary.public_constants.bind(py))?;
        fields.set_item(
            "external_sql_reference_resolver",
            self.boundary.external_sql_reference_resolver.bind(py),
        )?;
        fields.set_item(
            "effective_settings",
            self.compiler.effective_settings.bind(py),
        )?;
        fields.set_item("seed_inputs", self.compiler.seed_inputs.bind(py))?;
        fields.set_item("source_inputs", self.compiler.source_inputs.bind(py))?;
        fields.set_item(
            "sql_function_inputs",
            self.compiler.sql_function_inputs.bind(py),
        )?;
        fields.set_item("test_inputs", self.compiler.test_inputs.bind(py))?;
        fields.set_item("scenario_inputs", self.compiler.scenario_inputs.bind(py))?;
        fields.set_item("audit_inputs", self.compiler.audit_inputs.bind(py))?;
        fields.set_item("diagnostics", self.compiler.diagnostics.bind(py))?;
        fields.set_item("scope_index", self.compiler.scope_index.bind(py))?;
        fields.set_item(
            "declaration_scope",
            self.compiler.declaration_scope.bind(py),
        )?;
        Ok(fields)
    }
}

fn required<'py>(fields: &Bound<'py, PyDict>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    fields
        .get_item(name)?
        .ok_or_else(|| PyTypeError::new_err(format!("missing compile input field {name}")))
}

/// One compile's attached inputs, its model inputs projected from the owner.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeInputsView {
    owner: Py<NativeCompiledProject>,
    fields: InputsFields,
}

impl NativeInputsView {
    /// The view over `owner` with these input fields.
    pub(crate) fn new(
        owner: Py<NativeCompiledProject>,
        fields: &Bound<'_, PyDict>,
    ) -> PyResult<Self> {
        Ok(Self {
            owner,
            fields: InputsFields::from_fields(fields)?,
        })
    }
}

#[pymethods]
impl NativeInputsView {
    /// These inputs with `changes` applied; the owner's model inputs are shared.
    #[pyo3(signature = (**changes))]
    fn with_changes(&self, py: Python<'_>, changes: Option<Bound<'_, PyDict>>) -> PyResult<Self> {
        let current: Bound<'_, PyDict> = self.fields.as_fields(py)?;
        if let Some(changes) = changes {
            for (name, value) in changes.iter() {
                if !current.contains(&name)? {
                    return Err(PyTypeError::new_err(format!(
                        "unknown compile input field {name}"
                    )));
                }
                current.set_item(name, value)?;
            }
        }
        Self::new(self.owner.clone_ref(py), &current)
    }

    /// Every field by name, for an explicit `CompileProjectInputs` projection.
    fn fields<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let fields: Bound<'py, PyDict> = self.fields.as_fields(py)?;
        fields.set_item("native_project", self.owner.bind(py))?;
        Ok(fields)
    }

    #[getter]
    pub(crate) fn run_id(&self) -> String {
        self.fields.run_id.clone()
    }

    #[getter]
    pub(crate) fn effective_target_name(&self) -> Option<String> {
        self.fields.effective_target_name.clone()
    }

    #[getter(no_sql_validation)]
    pub(crate) fn is_sql_validation_skipped(&self) -> bool {
        self.fields.no_sql_validation
    }

    #[getter]
    pub(crate) fn model_inputs(&self, py: Python<'_>) -> Py<PyTuple> {
        self.fields.model_inputs.clone_ref(py)
    }

    #[getter]
    pub(crate) fn native_project(&self, py: Python<'_>) -> Py<NativeCompiledProject> {
        self.owner.clone_ref(py)
    }

    #[getter]
    pub(crate) fn project_config(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.project_config.clone_ref(py)
    }

    #[getter]
    pub(crate) fn local_config(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.local_config.clone_ref(py)
    }

    #[getter]
    pub(crate) fn discovered_inputs(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.discovered_inputs.clone_ref(py)
    }

    #[getter]
    pub(crate) fn sql_lexical_syntax(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.sql_lexical_syntax.clone_ref(py)
    }

    #[getter]
    pub(crate) fn effective_target(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.effective_target.clone_ref(py)
    }

    #[getter]
    pub(crate) fn compile_cache_dir(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.compile_cache_dir.clone_ref(py)
    }

    #[getter]
    pub(crate) fn effective_connection(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.effective_connection.clone_ref(py)
    }

    #[getter]
    pub(crate) fn effective_vars(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.effective_vars.clone_ref(py)
    }

    #[getter]
    pub(crate) fn macro_context(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.macro_context.clone_ref(py)
    }

    #[getter]
    pub(crate) fn loaded_macros(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.loaded_macros.clone_ref(py)
    }

    #[getter]
    pub(crate) fn public_enums(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.public_enums.clone_ref(py)
    }

    #[getter]
    pub(crate) fn public_constants(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.boundary.public_constants.clone_ref(py)
    }

    #[getter]
    pub(crate) fn external_sql_reference_resolver(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields
            .boundary
            .external_sql_reference_resolver
            .clone_ref(py)
    }

    #[getter]
    pub(crate) fn effective_settings(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.effective_settings.clone_ref(py)
    }

    #[getter]
    pub(crate) fn seed_inputs(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.seed_inputs.clone_ref(py)
    }

    #[getter]
    pub(crate) fn source_inputs(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.source_inputs.clone_ref(py)
    }

    #[getter]
    pub(crate) fn sql_function_inputs(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.sql_function_inputs.clone_ref(py)
    }

    #[getter]
    pub(crate) fn test_inputs(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.test_inputs.clone_ref(py)
    }

    #[getter]
    pub(crate) fn scenario_inputs(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.scenario_inputs.clone_ref(py)
    }

    #[getter]
    pub(crate) fn audit_inputs(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.audit_inputs.clone_ref(py)
    }

    #[getter]
    pub(crate) fn diagnostics(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.diagnostics.clone_ref(py)
    }

    #[getter]
    pub(crate) fn scope_index(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.scope_index.clone_ref(py)
    }

    #[getter]
    pub(crate) fn declaration_scope(&self, py: Python<'_>) -> Py<PyAny> {
        self.fields.compiler.declaration_scope.clone_ref(py)
    }
}
