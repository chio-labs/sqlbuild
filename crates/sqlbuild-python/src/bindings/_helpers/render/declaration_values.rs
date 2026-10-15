//! Declaration scope resolvers, per-path declaration contexts and adapter-rendered constants.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyInt, PyList, PyString, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::scopes::scope_lookup::build_scope_lookup;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const SCOPE_MODELS_MODULE: &str = "sqlbuild._native";
const SCOPE_TYPES_MODULE: &str = "sqlbuild._native";
const NATIVE_MODULE: &str = "sqlbuild._native";
const DISCOVERY_MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";
const SCOPE_ERRORS_MODULE: &str = "sqlbuild._native";
const NO_DECLARATION_KIND: u8 = 255;
/// Declaration kinds by their native code: enum 0, constant 1, macro 2.
const DECLARATION_KINDS: [&str; 3] = ["ENUM", "CONSTANT", "MACRO"];
const SQL_VALUE_ERRORS_MODULE: &str = "sqlbuild.sql_values.exceptions";
const TYPES_MODULE: &str = "types";
const SCALAR_KINDS: [&str; 6] = ["string", "integer", "boolean", "float", "decimal", "null"];
const COLLECTION_KINDS: [&str; 2] = ["list", "set"];
const ARRAY_RENDERING: &str = "array";
const MAX_SQL_VALUE_SIZE: usize = 1_000_000;

/// `(kind, name, owner)` identity of one declaration, built as `DeclarationIdentity`.
fn declaration_identity<'py>(
    classes: &(Bound<'py, PyAny>, Bound<'py, PyAny>),
    kind: &str,
    name: &Bound<'py, PyAny>,
    owner: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let (identity_class, kinds) = classes;
    let kind: Bound<'py, PyAny> = kinds.getattr(kind)?;
    match owner {
        Some(owner) => identity_class.call1((kind, name, owner)),
        None => identity_class.call1((kind, name)),
    }
}

/// Each project declaration's identity mapped to its process-local value.
fn runtime_declarations<'py>(
    discovered: &Bound<'py, PyAny>,
    loaded_macros: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = discovered.py();
    let classes = (
        imported(py, SCOPE_MODELS_MODULE, "DeclarationIdentity")?,
        imported(py, SCOPE_TYPES_MODULE, "DeclarationKind")?,
    );
    let declarations: Bound<'py, PyDict> = PyDict::new(py);
    for (files, kind) in [("enum_files", "ENUM"), ("constant_files", "CONSTANT")] {
        for file in discovered.getattr(files)?.try_iter()? {
            for declaration in file?.getattr("declarations")?.try_iter()? {
                let declaration: Bound<'py, PyAny> = declaration?;
                let identity =
                    declaration_identity(&classes, kind, &declaration.getattr("name")?, None)?;
                declarations.set_item(identity, declaration)?;
            }
        }
    }
    let resource_identity: Bound<'py, PyAny> =
        imported(py, SCOPE_MODELS_MODULE, "ResourceIdentity")?;
    let model_kind: Bound<'py, PyAny> =
        imported(py, SCOPE_TYPES_MODULE, "ResourceKind")?.getattr("MODEL")?;
    for model_file in discovered.getattr("model_files")?.try_iter()? {
        let model_file: Bound<'py, PyAny> = model_file?;
        let name: Bound<'py, PyAny> = model_file
            .getattr("header_values")?
            .call_method1("get", ("name",))?;
        let name: Bound<'py, PyAny> = if name.is_instance_of::<PyString>() && name.is_truthy()? {
            name
        } else {
            model_file.getattr("relative_path")?.getattr("stem")?
        };
        let owner: Bound<'py, PyAny> = resource_identity.call1((&model_kind, name))?;
        for (attribute, kind) in [
            ("enum_declarations", "ENUM"),
            ("constant_declarations", "CONSTANT"),
        ] {
            for declaration in model_file.getattr(attribute)?.try_iter()? {
                let declaration: Bound<'py, PyAny> = declaration?;
                let identity = declaration_identity(
                    &classes,
                    kind,
                    &declaration.getattr("name")?,
                    Some(&owner),
                )?;
                declarations.set_item(identity, declaration)?;
            }
        }
    }
    if !loaded_macros.is_none() {
        for name_and_macro in loaded_macros.call_method0("values")?.try_iter()? {
            let declared_macro: Bound<'py, PyAny> = name_and_macro?;
            let identity =
                declaration_identity(&classes, "MACRO", &declared_macro.getattr("name")?, None)?;
            declarations.set_item(identity, declared_macro)?;
        }
    }
    Ok(declarations)
}

/// Resources whose declarations differ from their directory's: private owners and grantees.
fn resource_specific<'py>(scope_index: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyFrozenSet>> {
    let py: Python<'py> = scope_index.py();
    let private: Bound<'py, PyAny> =
        imported(py, SCOPE_TYPES_MODULE, "ScopeKind")?.getattr("PRIVATE")?;
    let mut resources: Vec<Bound<'py, PyAny>> = Vec::new();
    for declaration in scope_index.getattr("declarations")?.try_iter()? {
        let declaration: Bound<'py, PyAny> = declaration?;
        let owner: Bound<'py, PyAny> = declaration.getattr("identity")?.getattr("owner")?;
        if declaration.getattr("scope")?.is(&private) && !owner.is_none() {
            resources.push(owner);
        }
    }
    for grant in scope_index.getattr("grants")?.try_iter()? {
        resources.push(grant?.getattr("resource")?);
    }
    PyFrozenSet::new(py, resources)
}

/// Pair the serializable static index with original process-local declaration values.
pub(crate) fn declaration_scope_resolver<'py>(
    discovered: &Bound<'py, PyAny>,
    scope_index: &Bound<'py, PyAny>,
    (loaded_macros, lookup): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let declarations: Bound<'py, PyDict> = runtime_declarations(discovered, loaded_macros)?;
    let lookup: Bound<'py, PyAny> = if lookup.is_none() {
        build_scope_lookup(py, scope_index)?.into_bound(py)
    } else {
        lookup.clone()
    };
    let projection: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "DeclarationRuntimeProjection")?,
        &[(
            "declarations",
            imported(py, TYPES_MODULE, "MappingProxyType")?.call1((&declarations,))?,
        )],
    )?;
    let native_contexts: Bound<'py, PyAny> =
        native_declaration_contexts(&lookup, declarations.as_any())?;
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "DeclarationScopeResolver")?,
        &[
            ("project_dir", discovered.getattr("project_dir")?),
            ("lookup", lookup),
            ("projection", projection),
            (
                "resource_specific",
                resource_specific(scope_index)?.into_any(),
            ),
            ("native_contexts", native_contexts),
        ],
    )
}

/// The native code of declaration kind `kind`, or the no-kind code.
fn kind_code(kinds: &[Bound<'_, PyAny>], kind: &Bound<'_, PyAny>) -> u8 {
    for (code, known) in (0_u8..).zip(kinds.iter()) {
        if known.is(kind) {
            return code;
        }
    }
    NO_DECLARATION_KIND
}

/// The native kind code of a runtime declaration value, by its class.
fn value_kind_code(classes: &[Bound<'_, PyAny>], value: &Bound<'_, PyAny>) -> PyResult<u8> {
    for (code, class) in (0_u8..).zip(classes.iter()) {
        if value.is_instance(class)? {
            return Ok(code);
        }
    }
    Ok(NO_DECLARATION_KIND)
}

/// `{owner: list(items)}` of an index position mapping.
fn listed_positions<'py>(positions: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let listed: Bound<'py, PyDict> = PyDict::new(positions.py());
    for item in positions.call_method0("items")?.try_iter()? {
        let (owner, items): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        listed.set_item(
            owner,
            PyList::new(
                positions.py(),
                items.try_iter()?.collect::<PyResult<Vec<_>>>()?,
            )?,
        )?;
    }
    Ok(listed)
}

/// Hand the lookup's declaration positions and runtime values to the native classifier.
pub(crate) fn native_declaration_contexts<'py>(
    lookup: &Bound<'py, PyAny>,
    declarations: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = lookup.py();
    let kind_type: Bound<'py, PyAny> = imported(py, SCOPE_TYPES_MODULE, "DeclarationKind")?;
    let kinds: Vec<Bound<'py, PyAny>> = DECLARATION_KINDS
        .iter()
        .map(|kind| kind_type.getattr(*kind))
        .collect::<PyResult<_>>()?;
    let value_classes: Vec<Bound<'py, PyAny>> = vec![
        imported(py, DISCOVERY_MODELS_MODULE, "EnumDeclaration")?,
        imported(py, DISCOVERY_MODELS_MODULE, "ConstantDeclaration")?,
        imported(py, COMPILE_MODELS_MODULE, "LoadedMacro")?,
    ];
    let index: Bound<'py, PyAny> = lookup.getattr("visibility_index")?;
    let lookup_declarations: Bound<'py, PyAny> = lookup.getattr("declarations")?;
    let identity_keys: Bound<'py, PyDict> = PyDict::new(py);
    let mut positions: Vec<Bound<'py, PyTuple>> = Vec::new();
    for identity in index.getattr("identities")?.try_iter()? {
        let identity: Bound<'py, PyAny> = identity?;
        let key: Bound<'py, PyAny> =
            identity_keys.call_method1("setdefault", (&identity, identity_keys.len()))?;
        let value: Bound<'py, PyAny> = declarations.call_method1("get", (&identity,))?;
        positions.push(PyTuple::new(
            py,
            [
                identity.clone(),
                lookup_declarations.get_item(&identity)?.get_item(0)?,
                identity.getattr("name")?,
                kind_code(&kinds, &identity.getattr("kind")?)
                    .into_pyobject(py)?
                    .into_any(),
                value.clone(),
                value_kind_code(&value_classes, &value)?
                    .into_pyobject(py)?
                    .into_any(),
                key,
            ],
        )?);
    }
    let reasons: Bound<'py, PyDict> = PyDict::new(py);
    for reason in imported(py, SCOPE_TYPES_MODULE, "VisibilityReason")?.try_iter()? {
        let reason: Bound<'py, PyAny> = reason?;
        reasons.set_item(reason.getattr("value")?, reason)?;
    }
    let classes: Bound<'py, PyDict> = PyDict::new(py);
    classes.set_item(
        "visibility_record",
        imported(py, SCOPE_MODELS_MODULE, "VisibilityRecord")?,
    )?;
    classes.set_item(
        "resolution_context",
        imported(py, COMPILE_MODELS_MODULE, "DeclarationResolutionContext")?,
    )?;
    classes.set_item("reasons", reasons)?;
    let keys: Bound<'py, PyDict> = PyDict::new(py);
    keys.set_item("identity_keys", identity_keys)?;
    keys.set_item("private_positions", index.getattr("private_positions")?)?;
    keys.set_item("grants_by_resource", lookup.getattr("grants_by_resource")?)?;
    let lookups: Bound<'py, PyDict> = PyDict::new(py);
    lookups.set_item("resources_by_path", lookup.getattr("resources_by_path")?)?;
    lookups.set_item("resources", lookup.getattr("resources")?)?;
    lookups.set_item("declarations", &lookup_declarations)?;
    lookups.set_item(
        "index_declarations",
        lookup.getattr("index")?.getattr("declarations")?,
    )?;
    for (name, class) in [
        ("resource_record", "ResourceRecord"),
        ("ownership_root", "OwnershipRoot"),
        ("resource_identity", "ResourceIdentity"),
        ("declaration_identity", "DeclarationIdentity"),
    ] {
        lookups.set_item(name, imported(py, SCOPE_MODELS_MODULE, class)?)?;
    }
    lookups.set_item(
        "resource_kind",
        imported(py, SCOPE_TYPES_MODULE, "ResourceKind")?,
    )?;
    lookups.set_item("declaration_kind", kind_type)?;
    lookups.set_item(
        "private_scope",
        imported(py, SCOPE_TYPES_MODULE, "ScopeKind")?.getattr("PRIVATE")?,
    )?;
    lookups.set_item(
        "identity_error",
        imported(py, SCOPE_ERRORS_MODULE, "InvalidQualifiedIdentityError")?,
    )?;
    lookups.set_item(
        "path_error",
        imported(py, SCOPE_ERRORS_MODULE, "InvalidScopePathError")?,
    )?;
    let global_positions: Bound<'py, PyList> = PyList::new(
        py,
        index
            .getattr("global_positions")?
            .try_iter()?
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    imported(py, NATIVE_MODULE, "NativeDeclarationContexts")?.call1((
        PyList::new(py, positions)?,
        (
            global_positions,
            listed_positions(&index.getattr("local_positions")?)?,
            listed_positions(&index.getattr("inherited_positions")?)?,
        ),
        classes,
        (keys, lookups),
    ))
}

/// Hand one scope lookup's positions and runtime values to the native classifier.
#[pyfunction]
#[pyo3(signature = (*, lookup, declarations))]
fn build_native_declaration_contexts<'py>(
    lookup: &Bound<'py, PyAny>,
    declarations: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    native_declaration_contexts(lookup, declarations)
}

/// Canonical visibility for one authored path, projected onto runtime declaration values.
pub(crate) fn resolved_declaration_context<'py>(
    resolver: &Bound<'py, PyAny>,
    file_path: &Bound<'py, PyAny>,
    resource: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = resolver.py();
    let resource: Bound<'py, PyAny> =
        resource.map_or_else(|| py.None().into_bound(py), Clone::clone);
    resolver
        .getattr("native_contexts")?
        .call_method1("resolve", (resolver, file_path, resource))?
        .get_item(0)
}

/// The adapter's SQL for one constant under `selected` collection rendering, or its error.
fn rendered_constant<'py>(
    declaration: &Bound<'py, PyAny>,
    value_renderer: &Bound<'py, PyAny>,
    selected: &Bound<'py, PyAny>,
) -> PyResult<String> {
    let value: Bound<'py, PyAny> = declaration.getattr("value")?;
    let kind: String = value.getattr("kind")?.str()?.extract()?;
    let method: &str = if SCALAR_KINDS.contains(&kind.as_str()) {
        "render_typed_scalar"
    } else if COLLECTION_KINDS.contains(&kind.as_str()) {
        if selected.eq(ARRAY_RENDERING)? {
            "render_typed_array"
        } else {
            "render_typed_value_list"
        }
    } else {
        "render_typed_object"
    };
    let rendered: String =
        call_with(&value_renderer.getattr(method)?, &[("value", value)])?.extract()?;
    let size: usize = rendered.len();
    if size > MAX_SQL_VALUE_SIZE {
        let context: String = format!(
            "{} constant '{}'",
            declaration.getattr("relative_path")?.str()?,
            declaration.getattr("name")?.str()?
        );
        return Err(PyErr::from_value(
            imported(declaration.py(), NATIVE_MODULE, "SqlValueValidationError")?
            .call1((format!(
                "{context} rendered value is {size} bytes; maximum is {MAX_SQL_VALUE_SIZE} bytes"
            ),))?,
        ));
    }
    Ok(rendered)
}

/// Render one validated constant with the active adapter's typed-value contract.
pub(crate) fn constant_declaration_sql<'py>(
    declaration: &Bound<'py, PyAny>,
    value_renderer: &Bound<'py, PyAny>,
    (collection_rendering, file_path): (&Bound<'py, PyAny>, Option<&Bound<'py, PyAny>>),
) -> PyResult<String> {
    let py: Python<'py> = declaration.py();
    let render_as: Bound<'py, PyAny> = declaration.getattr("render_as")?;
    let selected: Bound<'py, PyAny> = if render_as.is_truthy()? {
        render_as
    } else {
        collection_rendering.clone()
    };
    let error: PyErr = match rendered_constant(declaration, value_renderer, &selected) {
        Ok(rendered) => return Ok(rendered),
        Err(error) => error,
    };
    let rendering_error: Bound<'py, PyAny> =
        imported(py, SQL_VALUE_ERRORS_MODULE, "SqlValueRenderingError")?;
    let validation_error: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "SqlValueValidationError")?;
    let raised: Bound<'py, PyAny> = error.value(py).clone().into_any();
    if !(raised.is_instance(&rendering_error)? || raised.is_instance(&validation_error)?) {
        return Err(error);
    }
    let relative_path: Bound<'py, PyAny> = declaration.getattr("relative_path")?;
    let location: Bound<'py, PyAny> = match file_path {
        Some(file_path) if !file_path.is_none() => file_path.clone(),
        _ => relative_path.clone(),
    };
    let compile_error: Bound<'py, PyAny> =
        imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?.call1((format!(
            "{} constant '{}' could not be rendered in '{}' by adapter '{}' as {}: {}",
            relative_path.str()?,
            declaration.getattr("name")?.str()?,
            location.str()?,
            value_renderer.getattr("adapter_name")?.str()?,
            selected.getattr("value")?.str()?,
            raised.str()?,
        ),))?;
    compile_error.setattr("__cause__", &raised)?;
    Err(PyErr::from_value(compile_error))
}

/// Render one validated constant with the active adapter's typed-value contract.
#[pyfunction]
#[pyo3(signature = (*, declaration, value_renderer, collection_rendering, file_path=None))]
fn render_constant_declaration<'py>(
    declaration: &Bound<'py, PyAny>,
    value_renderer: &Bound<'py, PyAny>,
    collection_rendering: &Bound<'py, PyAny>,
    file_path: Option<Bound<'py, PyAny>>,
) -> PyResult<String> {
    constant_declaration_sql(
        declaration,
        value_renderer,
        (collection_rendering, file_path.as_ref()),
    )
}

/// One enum member value as a SQL scalar literal.
#[pyfunction]
#[pyo3(signature = (*, value))]
fn render_enum_member_value(value: &Bound<'_, PyAny>) -> PyResult<String> {
    if value.is_instance_of::<PyInt>() {
        return value.str()?.extract();
    }
    let text: String = value.extract()?;
    Ok(format!("'{}'", text.replace('\'', "''")))
}

/// Canonical visibility for one authored path, projected onto runtime declaration values.
#[pyfunction]
#[pyo3(signature = (*, resolver, file_path, resource=None))]
fn resolve_declaration_context<'py>(
    resolver: &Bound<'py, PyAny>,
    file_path: &Bound<'py, PyAny>,
    resource: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    resolved_declaration_context(resolver, file_path, resource.as_ref())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_native_declaration_contexts, module)?)?;
    module.add_function(wrap_pyfunction!(render_constant_declaration, module)?)?;
    module.add_function(wrap_pyfunction!(render_enum_member_value, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_declaration_context, module)?)?;
    Ok(())
}
