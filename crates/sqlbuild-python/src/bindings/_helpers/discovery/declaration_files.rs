//! Native declaration collections as the plain data the Python discovery facade materialises.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{IntoPyObjectExt, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_discovery::declaration_files::main::discover_declaration_collection::discover_declaration_collection;
use sqlbuild_discovery::declaration_files::main::parse_declaration_text::parse_declaration_text;
use sqlbuild_discovery::declaration_files::main::retained_collection::retained_collection;
use sqlbuild_discovery::declaration_files::models::{
    AuditFile, CollectionFailure, CollectionKind, CollectionRequest, ConstantFile,
    DeclarationCollection, DeclarationFileOptions, DiscoverySession, EnumFile, FileScope,
    FunctionFile, HookFile, MacroFile, ParsedDeclarationText, SchemaFile, ScopedFile, SeedFile,
};
use sqlbuild_discovery::declaration_files::types::Collection;
use sqlbuild_discovery::models::{DiscoveryFailure, FileOutcome, LineColumnSpan, ProjectRoot};
use sqlbuild_discovery::tree::models::ProjectTree;
use sqlbuild_sqltext::compiler::models::AuthoredValue;
use std::path::PathBuf;
use std::sync::Arc;

use crate::bindings::_helpers::discovery::project_files::{
    PyObject, failure_object, object, path_object, python_semantics, read_object,
    stage_failure_object, tuple_object,
};
use crate::bindings::_helpers::sqltext::authored_values::map_to_python;
use crate::bindings::models::{
    DeclarationDiscoveryRequest, DeclarationTextRequest, NativeDiscoverySession, NativeProjectTree,
};
use crate::bindings::types::CompilerDetach;

type Located = (String, usize, usize, usize, usize);

fn collection_kind(kind: &str) -> PyResult<CollectionKind> {
    CollectionKind::from_name(kind)
        .ok_or_else(|| PyValueError::new_err(format!("unknown declaration collection {kind:?}")))
}

fn ok_object(py: Python<'_>, mut items: Vec<PyObject>) -> PyResult<PyObject> {
    items.insert(0, object(py, "ok")?);
    tuple_object(py, items)
}

fn values_object(py: Python<'_>, values: &[(String, AuthoredValue)]) -> PyResult<PyObject> {
    map_to_python(py, values.to_vec())
}

/// `{key: value}`, or `{}` when the value is absent, for Python to project and read back.
fn single_value_object(
    py: Python<'_>,
    key: &str,
    value: Option<&AuthoredValue>,
) -> PyResult<PyObject> {
    map_to_python(
        py,
        value
            .map(|value| vec![(key.to_owned(), value.clone())])
            .unwrap_or_default(),
    )
}

fn failure_or_none(py: Python<'_>, failure: Option<&DiscoveryFailure>) -> PyResult<PyObject> {
    failure
        .map(|failure| failure_object(py, failure.clone()))
        .transpose()?
        .into_py_any(py)
}

fn enum_object(py: Python<'_>, file: &EnumFile) -> PyResult<PyObject> {
    let declarations: Vec<PyObject> = file
        .declarations
        .iter()
        .map(|declaration| {
            tuple_object(
                py,
                vec![
                    object(py, &declaration.name)?,
                    values_object(py, &declaration.members)?,
                    object(py, declaration.scalar_type)?,
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    ok_object(
        py,
        vec![object(py, &file.contents)?, object(py, declarations)?],
    )
}

fn constant_object(py: Python<'_>, file: &ConstantFile) -> PyResult<PyObject> {
    let declarations: Vec<PyObject> = file
        .declarations
        .iter()
        .map(|declaration| {
            tuple_object(
                py,
                vec![
                    object(py, &declaration.name)?,
                    single_value_object(py, "value", Some(&declaration.value))?,
                    object(py, &declaration.explicit_type)?,
                    object(py, &declaration.render_as)?,
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    ok_object(
        py,
        vec![
            object(py, &file.contents)?,
            object(py, declarations)?,
            failure_or_none(py, file.failure.as_ref())?,
        ],
    )
}

fn schema_object(py: Python<'_>, file: &SchemaFile) -> PyResult<PyObject> {
    let declarations: Vec<PyObject> = file
        .declarations
        .iter()
        .map(|declaration| {
            let locations: Vec<Located> =
                declaration.column_locations.iter().map(located).collect();
            tuple_object(
                py,
                vec![
                    object(py, &declaration.name)?,
                    object(py, &declaration.description)?,
                    object(py, &declaration.extends)?,
                    single_value_object(py, "columns", declaration.columns.as_ref())?,
                    object(py, locations)?,
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    ok_object(
        py,
        vec![
            object(py, &file.contents)?,
            object(py, declarations)?,
            failure_or_none(py, file.failure.as_ref())?,
        ],
    )
}

fn located((name, span): &(String, LineColumnSpan)) -> Located {
    (
        name.clone(),
        span.line,
        span.column,
        span.end_line,
        span.end_column,
    )
}

fn audit_object(py: Python<'_>, file: &AuditFile) -> PyResult<PyObject> {
    let blocks: Vec<PyObject> = file
        .blocks
        .iter()
        .map(|block| {
            tuple_object(
                py,
                vec![
                    object(py, block.audit_index)?,
                    values_object(py, &block.header_values)?,
                    object(py, &block.sql_body)?,
                    object(py, &block.name)?,
                    object(py, block.evaluation_mode)?,
                    object(py, &block.measure_sql)?,
                    object(py, &block.evidence_sql)?,
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    ok_object(py, vec![object(py, &file.contents)?, object(py, blocks)?])
}

fn hook_object(py: Python<'_>, file: &HookFile) -> PyResult<PyObject> {
    ok_object(
        py,
        vec![
            object(py, &file.contents)?,
            values_object(py, &file.header_values)?,
            object(py, &file.sql_body)?,
            object(py, &file.name)?,
            object(py, &file.description)?,
        ],
    )
}

fn function_object(py: Python<'_>, file: &FunctionFile) -> PyResult<PyObject> {
    ok_object(
        py,
        vec![
            object(py, &file.contents)?,
            values_object(py, &file.header_values)?,
            object(py, &file.body_sql)?,
        ],
    )
}

fn macro_object(py: Python<'_>, file: &MacroFile) -> PyResult<PyObject> {
    ok_object(py, vec![object(py, &file.contents)?])
}

fn seed_object(py: Python<'_>, _file: &SeedFile) -> PyResult<PyObject> {
    ok_object(py, Vec::new())
}

fn outcome_object<T>(
    py: Python<'_>,
    outcome: &FileOutcome<T>,
    parsed: fn(Python<'_>, &T) -> PyResult<PyObject>,
) -> PyResult<PyObject> {
    match outcome {
        FileOutcome::Parsed(value) => parsed(py, value),
        FileOutcome::Failed(failure) => failure_object(py, failure.clone()),
        FileOutcome::Unreadable(failure) => read_object(py, failure.clone()),
    }
}

/// `(declaration kind, scope kind, ownership root, owning path, declaration root)`.
fn scope_object(py: Python<'_>, tree: &ProjectTree, scope: &FileScope) -> PyResult<PyObject> {
    let path = |path: &Option<String>| -> PyResult<PyObject> {
        path.as_ref()
            .map(|path| path_object(py, tree, path.clone()))
            .transpose()?
            .into_py_any(py)
    };
    tuple_object(
        py,
        vec![
            object(py, scope.declaration_kind)?,
            object(py, scope.scope_kind)?,
            path(&scope.ownership_root)?,
            path(&scope.owning_path)?,
            path(&scope.declaration_root)?,
        ],
    )
}

/// Each file as `(relative_path, scope, payload)`, or the collection's failure payload.
fn collection_object<T>(
    py: Python<'_>,
    tree: &ProjectTree,
    collection: &Collection<T>,
    parsed: fn(Python<'_>, &T) -> PyResult<PyObject>,
) -> PyResult<PyObject> {
    let files = match collection {
        Ok(files) => files,
        Err(CollectionFailure::Stage(failure)) => {
            return stage_failure_object(py, tree, failure.clone());
        }
        Err(CollectionFailure::Layout(failure)) => return failure_object(py, failure.clone()),
    };
    files
        .iter()
        .map(|scoped| scoped_file_object(py, tree, scoped, parsed))
        .collect::<PyResult<Vec<PyObject>>>()?
        .into_py_any(py)
}

/// `(relative_path, scope, payload)` of one file.
fn scoped_file_object<T>(
    py: Python<'_>,
    tree: &ProjectTree,
    scoped: &ScopedFile<T>,
    parsed: fn(Python<'_>, &T) -> PyResult<PyObject>,
) -> PyResult<PyObject> {
    let scope: PyObject = scoped
        .scope
        .as_ref()
        .map(|scope| scope_object(py, tree, scope))
        .transpose()?
        .into_py_any(py)?;
    tuple_object(
        py,
        vec![
            path_object(py, tree, scoped.file.relative_path.clone())?,
            scope,
            outcome_object(py, &scoped.file.outcome, parsed)?,
        ],
    )
}

fn declaration_collection_object(
    py: Python<'_>,
    tree: &ProjectTree,
    collection: &DeclarationCollection,
) -> PyResult<PyObject> {
    match collection {
        DeclarationCollection::Enums(files) => collection_object(py, tree, files, enum_object),
        DeclarationCollection::Constants(files) => {
            collection_object(py, tree, files, constant_object)
        }
        DeclarationCollection::ModelSchemas(files) => {
            collection_object(py, tree, files, schema_object)
        }
        DeclarationCollection::SqlFunctions(files) => {
            collection_object(py, tree, files, function_object)
        }
        DeclarationCollection::SqlHooks(files) => collection_object(py, tree, files, hook_object),
        DeclarationCollection::Audits(files) => collection_object(py, tree, files, audit_object),
        DeclarationCollection::Seeds(files) => collection_object(py, tree, files, seed_object),
        DeclarationCollection::Macros(files) => collection_object(py, tree, files, macro_object),
    }
}

fn options(
    (function_keys, audit_keys, hook_keys): (Vec<String>, Vec<String>, Vec<String>),
    python_version: (u8, u8),
    unicode_version: &str,
) -> PyResult<DeclarationFileOptions> {
    Ok(DeclarationFileOptions {
        function_keys,
        audit_keys,
        hook_keys,
        python: python_semantics(python_version, unicode_version)?,
    })
}

#[pymethods]
impl NativeDiscoverySession {
    #[new]
    fn new(request: DeclarationDiscoveryRequest) -> PyResult<Self> {
        Ok(Self {
            inner: DiscoverySession::new(
                ProjectRoot {
                    directory: PathBuf::from(request.project_dir),
                    display_prefix: request.display_prefix,
                },
                options(
                    (request.function_keys, request.audit_keys, request.hook_keys),
                    request.python_version,
                    &request.unicode_version,
                )?,
            ),
        })
    }

    /// Discover the collection `kind` once per session: one payload per file, or its failure.
    #[pyo3(signature = (kind, tree, isolate_kind=false))]
    fn collection(
        &self,
        py: Python<'_>,
        kind: &str,
        tree: &NativeProjectTree,
        isolate_kind: bool,
    ) -> PyResult<PyObject> {
        let request = CollectionRequest {
            kind: collection_kind(kind)?,
            isolate_kind,
        };
        let collection: Arc<DeclarationCollection> = py
            .compiler_detach(|| {
                Ok(retained_collection(&self.inner, request, || {
                    discover_declaration_collection(&self.inner, &tree.inner, request)
                }))
            })
            .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
        declaration_collection_object(py, &tree.inner, &collection)
    }
}

/// Parse in-memory contents as discovery parses a `kind` declaration file named `file_path`.
#[pyfunction]
fn parse_declaration_contents(
    py: Python<'_>,
    request: DeclarationTextRequest,
    names: (String, String),
    contents: String,
) -> PyResult<PyObject> {
    let (file_path, hook_name): (String, String) = names;
    let kind: CollectionKind = collection_kind(&request.kind)?;
    let options: DeclarationFileOptions = options(
        (request.function_keys, request.audit_keys, request.hook_keys),
        request.python_version,
        &request.unicode_version,
    )?;
    let parsed: Option<FileOutcome<ParsedDeclarationText>> = py
        .compiler_detach(|| {
            Ok(parse_declaration_text(
                kind,
                (&file_path, &hook_name),
                contents,
                &options,
            ))
        })
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    let Some(outcome) = parsed else {
        return Err(PyValueError::new_err(format!(
            "{} files have no authored text to parse",
            kind.as_str()
        )));
    };
    outcome_object(py, &outcome, |py, parsed| match parsed {
        ParsedDeclarationText::Enum(file) => enum_object(py, file),
        ParsedDeclarationText::Constant(file) => constant_object(py, file),
        ParsedDeclarationText::ModelSchema(file) => schema_object(py, file),
        ParsedDeclarationText::SqlFunction(file) => function_object(py, file),
        ParsedDeclarationText::SqlHook(file) => hook_object(py, file),
        ParsedDeclarationText::Audit(file) => audit_object(py, file),
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeDiscoverySession>()?;
    module.add_function(wrap_pyfunction!(parse_declaration_contents, module)?)?;
    Ok(())
}
