//! Functions attached by the native loop, held by the compiled project, and their views.

use pyo3::exceptions::{PyIndexError, PyRuntimeError};
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{FromPyObject, pyclass, pymethods};

use crate::bindings::_helpers::compiled_project::compiled_model_view::{
    DestinationFact, defaulted_destination, object_key, relation_location,
};
use crate::bindings::_helpers::compiled_project::model_input_view::{
    InputViewClasses, reference_tuple, view_classes,
};
use crate::bindings::_helpers::compiled_project::model_loop_host::ReferenceRow;
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;

const TABLE_FUNCTION_TYPE: &str = "table_fn";
const SCALAR_FUNCTION_TYPE: &str = "udf";
const SQL_LANGUAGE: &str = "sql";
const PYTHON_LANGUAGE: &str = "python";
const FUNCTION_FILE_ATTRIBUTE: &str = "relative_path";
const FILE_PATH_ATTRIBUTE: &str = "file_path";
const NOT_ASSEMBLED: &str = "the function was not assembled";
const FUNCTION_CLASSES: &str = "functions";

/// The Python classes a function view projects its argument and return column records with.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct FunctionClasses<'py> {
    function_argument: Bound<'py, PyAny>,
    function_return_column: Bound<'py, PyAny>,
    function_language: Bound<'py, PyAny>,
}

/// `(name, type)` of an argument or return column, its types template-expanded.
pub(crate) type NamedTypeRow = (String, String);

/// `(node type, name, tags, references as (kind, name, package))`.
pub(crate) type FunctionAssemblyRow = (
    &'static str,
    String,
    Vec<String>,
    Vec<(String, String, Option<String>)>,
);

/// `(kind, name)` of a compiled object key.
pub(crate) type ObjectKeyRow = (String, String);

/// A Python function's runtime, entry point and packages.
pub(crate) struct PythonRuntime {
    pub(crate) runtime_version: Option<String>,
    pub(crate) entry_point: Option<String>,
    pub(crate) packages: Vec<String>,
}

/// What the function loop attached for one SQL or Python function.
pub(crate) struct AttachedFunction {
    /// The discovered function file.
    pub(crate) function_file: Py<PyAny>,
    /// The file's relative path, as messages name it.
    pub(crate) relative_path: String,
    pub(crate) name: String,
    pub(crate) arguments: Vec<NamedTypeRow>,
    pub(crate) returns: String,
    pub(crate) return_columns: Vec<NamedTypeRow>,
    /// The expanded SQL body, or the Python function's source.
    pub(crate) body: String,
    pub(crate) references: Vec<ReferenceRow>,
    /// The physical and logical destination.
    pub(crate) destination: DestinationFact,
    /// The destination the function's fingerprint reads.
    pub(crate) fingerprint_destination: DestinationFact,
    /// `None` for a SQL function.
    pub(crate) python: Option<PythonRuntime>,
    pub(crate) tags: Vec<String>,
    pub(crate) description: Option<String>,
    /// Usage records, the identities the scope index is built from.
    pub(crate) usages: Py<PyTuple>,
}

impl AttachedFunction {
    /// `function_node_type`: a table function when it declares return columns.
    pub(crate) fn node_type(&self) -> &'static str {
        if self.return_columns.is_empty() {
            SCALAR_FUNCTION_TYPE
        } else {
            TABLE_FUNCTION_TYPE
        }
    }
}

/// One attached function held by the compiled project.
pub(crate) struct FunctionRecord {
    pub(crate) attached: AttachedFunction,
    /// The dependency keys native project assembly resolved, once it ran.
    deps: Option<Vec<ObjectKeyRow>>,
    arguments: PyOnceLock<Py<PyTuple>>,
    return_columns: PyOnceLock<Py<PyTuple>>,
    references: PyOnceLock<Py<PyTuple>>,
    key: PyOnceLock<Py<PyAny>>,
}

impl FunctionRecord {
    pub(crate) fn new(attached: AttachedFunction) -> Self {
        Self {
            attached,
            deps: None,
            arguments: PyOnceLock::new(),
            return_columns: PyOnceLock::new(),
            references: PyOnceLock::new(),
            key: PyOnceLock::new(),
        }
    }

    /// Keep the dependency keys native project assembly resolved for the function.
    pub(crate) fn set_deps(&mut self, deps: Vec<ObjectKeyRow>) {
        self.deps = Some(deps);
    }

    fn named_types(
        rows: &[NamedTypeRow],
        class: &Bound<'_, PyAny>,
        cache: &PyOnceLock<Py<PyTuple>>,
    ) -> PyResult<Py<PyTuple>> {
        let py: Python<'_> = class.py();
        cache
            .get_or_try_init(py, || {
                let mut items: Vec<Bound<'_, PyAny>> = Vec::with_capacity(rows.len());
                for (name, type_text) in rows {
                    let fields: Bound<'_, PyDict> = PyDict::new(py);
                    fields.set_item("name", name)?;
                    fields.set_item("type", type_text)?;
                    items.push(class.call((), Some(&fields))?);
                }
                Ok::<_, pyo3::PyErr>(PyTuple::new(py, items)?.unbind())
            })
            .map(|items| items.clone_ref(py))
    }

    fn language<'py>(&self, classes: &FunctionClasses<'py>) -> PyResult<Bound<'py, PyAny>> {
        let value: &str = if self.attached.python.is_some() {
            PYTHON_LANGUAGE
        } else {
            SQL_LANGUAGE
        };
        classes.function_language.call1((value,))
    }
}

fn read_function<'py, T>(
    owner: &Py<NativeCompiledProject>,
    index: usize,
    py: Python<'py>,
    read: impl FnOnce(&FunctionRecord, Python<'py>) -> PyResult<T>,
) -> PyResult<T> {
    let owner = owner.bind(py).borrow();
    let function: &FunctionRecord = owner
        .functions()
        .get(index)
        .ok_or_else(|| PyIndexError::new_err(index))?;
    read(function, py)
}

fn function_classes<'py>(
    owner: &Py<NativeCompiledProject>,
    py: Python<'py>,
) -> PyResult<FunctionClasses<'py>> {
    owner
        .bind(py)
        .borrow()
        .input_classes(py)?
        .get_item(FUNCTION_CLASSES)?
        .extract()
}

/// The attributes a function's input and compiled views share.
macro_rules! function_getters {
    ($view:ty, { $($extra:tt)* }) => {
        #[pymethods]
        impl $view {
            $($extra)*

            #[getter]
            fn name(&self, py: Python<'_>) -> PyResult<String> {
                read_function(&self.owner, self.index, py, |function, _| {
                    Ok(function.attached.name.clone())
                })
            }

            #[getter]
            fn arguments(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
                let classes: FunctionClasses<'_> = function_classes(&self.owner, py)?;
                read_function(&self.owner, self.index, py, |function, _| {
                    FunctionRecord::named_types(
                        &function.attached.arguments,
                        &classes.function_argument,
                        &function.arguments,
                    )
                })
            }

            #[getter]
            fn returns(&self, py: Python<'_>) -> PyResult<String> {
                read_function(&self.owner, self.index, py, |function, _| {
                    Ok(function.attached.returns.clone())
                })
            }

            #[getter]
            fn body_sql(&self, py: Python<'_>) -> PyResult<String> {
                read_function(&self.owner, self.index, py, |function, _| {
                    Ok(function.attached.body.clone())
                })
            }

            #[getter]
            fn return_columns(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
                let classes: FunctionClasses<'_> = function_classes(&self.owner, py)?;
                read_function(&self.owner, self.index, py, |function, _| {
                    FunctionRecord::named_types(
                        &function.attached.return_columns,
                        &classes.function_return_column,
                        &function.return_columns,
                    )
                })
            }

            #[getter]
            fn references(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
                let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
                read_function(&self.owner, self.index, py, |function, _| {
                    reference_tuple(
                        &classes,
                        &function.attached.references,
                        &function.references,
                    )
                })
            }

            #[getter]
            fn language<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
                let classes: FunctionClasses<'py> = function_classes(&self.owner, py)?;
                read_function(&self.owner, self.index, py, |function, _| {
                    function.language(&classes)
                })
            }

            #[getter]
            fn runtime_version(&self, py: Python<'_>) -> PyResult<Option<String>> {
                read_function(&self.owner, self.index, py, |function, _| {
                    Ok(function
                        .attached
                        .python
                        .as_ref()
                        .and_then(|python| python.runtime_version.clone()))
                })
            }

            #[getter]
            fn entry_point(&self, py: Python<'_>) -> PyResult<Option<String>> {
                read_function(&self.owner, self.index, py, |function, _| {
                    Ok(function
                        .attached
                        .python
                        .as_ref()
                        .and_then(|python| python.entry_point.clone()))
                })
            }

            #[getter]
            fn packages<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
                read_function(&self.owner, self.index, py, |function, py| {
                    let packages: &[String] = function
                        .attached
                        .python
                        .as_ref()
                        .map_or(&[], |python| python.packages.as_slice());
                    PyTuple::new(py, packages)
                })
            }

            #[getter]
            fn tags<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
                read_function(&self.owner, self.index, py, |function, py| {
                    PyTuple::new(py, &function.attached.tags)
                })
            }

            #[getter]
            fn description(&self, py: Python<'_>) -> PyResult<Option<String>> {
                read_function(&self.owner, self.index, py, |function, _| {
                    Ok(function.attached.description.clone())
                })
            }
        }
    };
}

/// One attached function, read from the compiled project that owns it.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeFunctionInput {
    owner: Py<NativeCompiledProject>,
    index: usize,
}

impl NativeFunctionInput {
    pub(crate) fn new(owner: Py<NativeCompiledProject>, index: usize) -> Self {
        Self { owner, index }
    }
}

function_getters!(NativeFunctionInput, {
    #[getter]
    fn function_file(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        read_function(&self.owner, self.index, py, |function, py| {
            Ok(function.attached.function_file.clone_ref(py))
        })
    }

    #[getter]
    fn database(&self, py: Python<'_>) -> PyResult<Option<String>> {
        read_function(&self.owner, self.index, py, |function, _| {
            Ok(function.attached.destination.database.clone())
        })
    }

    #[getter]
    fn schema(&self, py: Python<'_>) -> PyResult<Option<String>> {
        read_function(&self.owner, self.index, py, |function, _| {
            Ok(function.attached.destination.schema.clone())
        })
    }

    #[getter]
    fn logical_database(&self, py: Python<'_>) -> PyResult<Option<String>> {
        read_function(&self.owner, self.index, py, |function, _| {
            Ok(function.attached.destination.logical_database.clone())
        })
    }

    #[getter]
    fn logical_schema(&self, py: Python<'_>) -> PyResult<Option<String>> {
        read_function(&self.owner, self.index, py, |function, _| {
            Ok(function.attached.destination.logical_schema.clone())
        })
    }

    #[getter]
    fn fingerprint_database(&self, py: Python<'_>) -> PyResult<Option<String>> {
        read_function(&self.owner, self.index, py, |function, _| {
            Ok(function.attached.fingerprint_destination.database.clone())
        })
    }

    #[getter]
    fn fingerprint_schema(&self, py: Python<'_>) -> PyResult<Option<String>> {
        read_function(&self.owner, self.index, py, |function, _| {
            Ok(function.attached.fingerprint_destination.schema.clone())
        })
    }

    #[getter]
    fn fingerprint_logical_database(&self, py: Python<'_>) -> PyResult<Option<String>> {
        read_function(&self.owner, self.index, py, |function, _| {
            Ok(function
                .attached
                .fingerprint_destination
                .logical_database
                .clone())
        })
    }

    #[getter]
    fn fingerprint_logical_schema(&self, py: Python<'_>) -> PyResult<Option<String>> {
        read_function(&self.owner, self.index, py, |function, _| {
            Ok(function
                .attached
                .fingerprint_destination
                .logical_schema
                .clone())
        })
    }

    #[getter]
    fn declaration_usages(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        read_function(&self.owner, self.index, py, |function, py| {
            Ok(function.attached.usages.clone_ref(py))
        })
    }

    /// `(node type, name, tags, references)`, what project assembly resolves dependencies from.
    #[getter]
    fn assembly_row(&self, py: Python<'_>) -> PyResult<FunctionAssemblyRow> {
        read_function(&self.owner, self.index, py, |function, _| {
            let attached: &AttachedFunction = &function.attached;
            Ok((
                attached.node_type(),
                attached.name.clone(),
                attached.tags.clone(),
                attached
                    .references
                    .iter()
                    .map(|(kind, name, package, _)| (kind.clone(), name.clone(), package.clone()))
                    .collect(),
            ))
        })
    }
});

/// One assembled function, read from the compiled project that owns it.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeCompiledFunction {
    owner: Py<NativeCompiledProject>,
    index: usize,
    /// The destination and fingerprint destination with target defaults applied.
    defaulted: Option<(DestinationFact, DestinationFact)>,
    destination: PyOnceLock<Py<PyAny>>,
    fingerprint_destination: PyOnceLock<Py<PyAny>>,
}

impl NativeCompiledFunction {
    pub(crate) fn new(owner: Py<NativeCompiledProject>, index: usize) -> Self {
        Self::defaulted(owner, index, None)
    }

    fn defaulted(
        owner: Py<NativeCompiledProject>,
        index: usize,
        defaulted: Option<(DestinationFact, DestinationFact)>,
    ) -> Self {
        Self {
            owner,
            index,
            defaulted,
            destination: PyOnceLock::new(),
            fingerprint_destination: PyOnceLock::new(),
        }
    }

    /// The destination and fingerprint destination, with target defaults once applied.
    fn current_destinations(&self, py: Python<'_>) -> PyResult<(DestinationFact, DestinationFact)> {
        if let Some(defaulted) = &self.defaulted {
            return Ok(defaulted.clone());
        }
        read_function(&self.owner, self.index, py, |function, _| {
            Ok((
                function.attached.destination.clone(),
                function.attached.fingerprint_destination.clone(),
            ))
        })
    }
}

function_getters!(NativeCompiledFunction, {
    /// The function's planner-facing `CompiledObjectKey`.
    #[getter]
    fn key(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        read_function(&self.owner, self.index, py, |function, py| {
            function
                .key
                .get_or_try_init(py, || {
                    object_key(
                        &classes.compiled,
                        function.attached.node_type(),
                        &function.attached.name,
                    )
                })
                .map(|key| key.clone_ref(py))
        })
    }

    /// The planner-facing keys of the resources the function reads.
    #[getter]
    fn deps<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        read_function(&self.owner, self.index, py, |function, py| {
            let deps: &[ObjectKeyRow] = function
                .deps
                .as_deref()
                .ok_or_else(|| PyRuntimeError::new_err(NOT_ASSEMBLED))?;
            let mut keys: Vec<Py<PyAny>> = Vec::with_capacity(deps.len());
            for (kind, name) in deps {
                keys.push(object_key(&classes.compiled, kind, name)?);
            }
            PyTuple::new(py, keys)
        })
    }

    #[getter]
    fn relative_path(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        read_function(&self.owner, self.index, py, |function, py| {
            Ok(function
                .attached
                .function_file
                .bind(py)
                .getattr(FUNCTION_FILE_ATTRIBUTE)?
                .unbind())
        })
    }

    #[getter]
    fn source_file_path(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        read_function(&self.owner, self.index, py, |function, py| {
            Ok(function
                .attached
                .function_file
                .bind(py)
                .getattr(FILE_PATH_ATTRIBUTE)?
                .unbind())
        })
    }

    /// The function's planner-facing `CompiledRelationLocation`.
    #[getter]
    fn destination(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.destination
            .get_or_try_init(py, || {
                relation_location(&classes.compiled, &self.current_destinations(py)?.0)
            })
            .map(|destination| destination.clone_ref(py))
    }

    /// The destination the function's fingerprint reads.
    #[getter]
    fn fingerprint_destination(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        self.fingerprint_destination
            .get_or_try_init(py, || {
                relation_location(&classes.compiled, &self.current_destinations(py)?.1)
            })
            .map(|destination| destination.clone_ref(py))
    }

    /// This function with target defaults; a non-inheriting Python function is name-qualified.
    fn with_target_defaults(
        &self,
        py: Python<'_>,
        defaults: (Option<String>, Option<String>),
        render: Bound<'_, PyAny>,
        python_functions_inherit_default_namespace: bool,
    ) -> PyResult<Self> {
        let python: bool = read_function(&self.owner, self.index, py, |function, _| {
            Ok(function.attached.python.is_some())
        })?;
        let apply: bool = !python || python_functions_inherit_default_namespace;
        let (current, fingerprint) = self.current_destinations(py)?;
        let fingerprint: DestinationFact =
            defaulted_destination(&fingerprint, defaults.clone(), &render)?;
        let defaults: (Option<String>, Option<String>) =
            if apply { defaults } else { (None, None) };
        let mut defaulted: DestinationFact = defaulted_destination(&current, defaults, &render)?;
        if !apply && defaulted.qualified_name.is_none() {
            defaulted.qualified_name = Some(defaulted.name.clone());
        }
        Ok(Self::defaulted(
            self.owner.clone_ref(py),
            self.index,
            Some((defaulted, fingerprint)),
        ))
    }
});
