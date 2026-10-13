//! Runtime SQL relation maps for Python node contexts and hard-coded name guards.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PySet, PySetMethods};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};

const REF_MODELS_MODULE: &str = "sqlbuild.python_nodes.models";
const REF_TYPES_MODULE: &str = "sqlbuild.python_nodes.types";
const QUALIFIED_NAME_MODULE: &str =
    "sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name";
const SOURCE_RELATION_MODULE: &str = "sqlbuild.compiler.references.main.render_source_relation";
const SHARED_EXCEPTIONS_MODULE: &str = "sqlbuild.errors.contracts.exceptions";

/// The `SqlResourceRefKind` members a relation map distinguishes.
struct RefKinds<'py> {
    model: Bound<'py, PyAny>,
    seed: Bound<'py, PyAny>,
    source: Bound<'py, PyAny>,
}

impl<'py> RefKinds<'py> {
    fn load(py: Python<'py>) -> PyResult<Self> {
        let kinds: Bound<'py, PyAny> = imported(py, REF_TYPES_MODULE, "SqlResourceRefKind")?;
        Ok(Self {
            model: kinds.getattr("MODEL")?,
            seed: kinds.getattr("SEED")?,
            source: kinds.getattr("SOURCE")?,
        })
    }
}

/// A `SharedInputError` with `message`.
fn shared_error(py: Python<'_>, message: String) -> PyErr {
    match imported(py, SHARED_EXCEPTIONS_MODULE, "SharedInputError")
        .and_then(|class| class.call1((message,)))
    {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// Return adapter-qualified runtime relations required by selected Python nodes.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_python_relation_targets<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyDict>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_python_relation_targets",
        options,
        (&["adapter", "project", "plan_output"], &["required_refs"]),
    )?;
    let kinds: RefKinds<'py> = RefKinds::load(py)?;
    let adapter: Bound<'py, PyAny> = arguments.value("adapter")?;
    let project: Bound<'py, PyAny> = arguments.value("project")?;
    let plan_output: Bound<'py, PyAny> = arguments.value("plan_output")?;
    let required: Bound<'py, PyAny> = arguments.value("required_refs")?;
    let refs: Bound<'py, PyAny> = if required.is_none() {
        planned_relation_refs(&plan_output, &kinds)?
    } else {
        required
    };
    let targets: Bound<'py, PyDict> = PyDict::new(py);
    for reference in refs.try_iter()? {
        let reference: Bound<'py, PyAny> = reference?;
        let relation: Bound<'py, PyAny> =
            resolved_relation((&adapter, &project, &plan_output), &reference, &kinds)?;
        targets.set_item(reference, relation)?;
    }
    Ok(targets)
}

/// Return every planned project relation for hard-coded name warnings, or None when off.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_project_relation_targets<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Option<Bound<'py, PyDict>>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_project_relation_targets",
        options,
        (&["adapter", "plan_output"], &[]),
    )?;
    let plan_output: Bound<'py, PyAny> = arguments.value("plan_output")?;
    if !plan_output
        .getattr("enforce_explicit_references")?
        .is_truthy()?
    {
        return Ok(None);
    }
    let kinds: RefKinds<'py> = RefKinds::load(py)?;
    let adapter: Bound<'py, PyAny> = arguments.value("adapter")?;
    let targets: Bound<'py, PyDict> = PyDict::new(py);
    for reference in planned_relation_refs(&plan_output, &kinds)?.try_iter()? {
        let reference: Bound<'py, PyAny> = reference?;
        let relation: Bound<'py, PyAny> =
            planned_relation(&adapter, &plan_output, &reference, &kinds)?;
        if !relation.is_none() {
            targets.set_item(reference, relation)?;
        }
    }
    Ok(Some(targets))
}

/// The model, seed and Python source refs of a plan, as the frozenset Python builds.
fn planned_relation_refs<'py>(
    plan_output: &Bound<'py, PyAny>,
    kinds: &RefKinds<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = plan_output.py();
    let reference: Bound<'py, PyAny> = imported(py, REF_MODELS_MODULE, "SqlResourceRef")?;
    let refs: Bound<'py, PySet> = PySet::empty(py)?;
    for (attribute, kind) in [
        ("model_locations", &kinds.model),
        ("seed_locations", &kinds.seed),
        ("python_source_entries", &kinds.source),
    ] {
        for name in plan_output.getattr(attribute)?.try_iter()? {
            refs.add(call_with(
                &reference,
                &[("kind", kind.clone()), ("name", name?)],
            )?)?;
        }
    }
    imported(py, "builtins", "frozenset")?.call1((refs,))
}

/// `_resolve_relation`: the planned relation, or the compiled location's qualified name.
fn resolved_relation<'py>(
    (adapter, project, plan_output): (&Bound<'py, PyAny>, &Bound<'py, PyAny>, &Bound<'py, PyAny>),
    reference: &Bound<'py, PyAny>,
    kinds: &RefKinds<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = adapter.py();
    let planned: Bound<'py, PyAny> = planned_relation(adapter, plan_output, reference, kinds)?;
    if !planned.is_none() {
        return Ok(planned);
    }
    let kind: Bound<'py, PyAny> = reference.getattr("kind")?;
    let name: Bound<'py, PyAny> = reference.getattr("name")?;
    if kind.eq(&kinds.source)? {
        return Err(shared_error(
            py,
            format!(
                "Python node source '{}' is missing from the resolved plan source map",
                name.str()?
            ),
        ));
    }
    let resources: Bound<'py, PyAny> = project.getattr(if kind.eq(&kinds.model)? {
        "models"
    } else {
        "seeds"
    })?;
    let mut location: Option<Bound<'py, PyAny>> = None;
    for resource in resources.try_iter()? {
        let resource: Bound<'py, PyAny> = resource?;
        if resource.getattr("name")?.eq(&name)? {
            location = Some(resource.getattr("destination")?);
            break;
        }
    }
    let Some(location) = location else {
        return Err(shared_error(
            py,
            format!(
                "Python node references unknown {} '{}'",
                kind.getattr("value")?.str()?,
                name.str()?
            ),
        ));
    };
    qualified_name(adapter, &location)
}

/// `resolve_relation_location_qualified_name(adapter=adapter, location=location)`.
fn qualified_name<'py>(
    adapter: &Bound<'py, PyAny>,
    location: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(
            adapter.py(),
            QUALIFIED_NAME_MODULE,
            "resolve_relation_location_qualified_name",
        )?,
        &[("adapter", adapter.clone()), ("location", location.clone())],
    )
}

/// `_planned_relation`: the relation the plan resolved for `reference`, or `None`.
fn planned_relation<'py>(
    adapter: &Bound<'py, PyAny>,
    plan_output: &Bound<'py, PyAny>,
    reference: &Bound<'py, PyAny>,
    kinds: &RefKinds<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = adapter.py();
    let kind: Bound<'py, PyAny> = reference.getattr("kind")?;
    let name: Bound<'py, PyAny> = reference.getattr("name")?;
    if kind.eq(&kinds.source)? {
        let source: Bound<'py, PyAny> = plan_output
            .getattr("python_source_entries")?
            .call_method1("get", (name,))?;
        if source.is_none() {
            return Ok(source);
        }
        return call_with(
            &imported(py, SOURCE_RELATION_MODULE, "render_source_relation")?,
            &[("entry", source), ("adapter", adapter.clone())],
        );
    }
    let locations: Bound<'py, PyAny> = plan_output.getattr(if kind.eq(&kinds.model)? {
        "model_locations"
    } else {
        "seed_locations"
    })?;
    let location: Bound<'py, PyAny> = locations.call_method1("get", (name,))?;
    if location.is_none() {
        return Ok(location);
    }
    qualified_name(adapter, &location)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_python_relation_targets, module)?)?;
    module.add_function(wrap_pyfunction!(build_project_relation_targets, module)?)
}
