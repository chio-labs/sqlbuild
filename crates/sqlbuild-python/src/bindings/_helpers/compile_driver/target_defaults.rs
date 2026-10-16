//! Adapter default schema and database applied to compiled relation locations.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyTuple;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::compiled_project::records::project_with;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

/// The adapter defaults every compiled location falls back to.
pub(crate) struct TargetDefaults<'py> {
    pub(crate) default_schema: Bound<'py, PyAny>,
    pub(crate) default_database: Bound<'py, PyAny>,
    pub(crate) render_qualified_name: Bound<'py, PyAny>,
    pub(crate) python_functions_inherit_default_namespace: Bound<'py, PyAny>,
}

impl<'py> TargetDefaults<'py> {
    /// `(default_schema, default_database)`.
    fn pair(&self) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            self.default_schema.py(),
            [self.default_schema.clone(), self.default_database.clone()],
        )
    }
}

/// `left or right`.
fn or_else<'py>(left: Bound<'py, PyAny>, right: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    Ok(if left.is_truthy()? {
        left
    } else {
        right.clone()
    })
}

/// Apply adapter default schema/database to compiled project targets.
pub(crate) fn apply_target_defaults<'py>(
    project: &Bound<'py, PyAny>,
    defaults: &TargetDefaults<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let compiled_model: Bound<'py, PyAny> = registry::class(py, RecordId::CompiledModel)?;
    let native_seed: Bound<'py, PyAny> = registry::native(py, NativeAttr::NativeCompiledSeed)?;
    let replace: Bound<'py, PyAny> = imported(py, "dataclasses", "replace")?;
    let mut models: Vec<Bound<'py, PyAny>> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        models.push(if model.is_instance(&compiled_model)? {
            replace.call(
                (&model,),
                Some(&keywords(
                    py,
                    &[(
                        "destination",
                        resolved_target(&model.getattr("destination")?, defaults)?,
                    )],
                )?),
            )?
        } else {
            model.call_method1(
                "with_target_defaults",
                (defaults.pair()?, &defaults.render_qualified_name),
            )?
        });
    }
    let mut seeds: Vec<Bound<'py, PyAny>> = Vec::new();
    for seed in project.getattr("seeds")?.try_iter()? {
        let seed: Bound<'py, PyAny> = seed?;
        seeds.push(if seed.is_instance(&native_seed)? {
            seed.call_method1(
                "with_target_defaults",
                (defaults.pair()?, &defaults.render_qualified_name),
            )?
        } else {
            replace.call(
                (&seed,),
                Some(&keywords(
                    py,
                    &[(
                        "destination",
                        resolved_target(&seed.getattr("destination")?, defaults)?,
                    )],
                )?),
            )?
        });
    }
    let mut functions: Vec<Bound<'py, PyAny>> = Vec::new();
    for function in project.getattr("functions")?.try_iter()? {
        functions.push(function?.call_method1(
            "with_target_defaults",
            (
                defaults.pair()?,
                &defaults.render_qualified_name,
                &defaults.python_functions_inherit_default_namespace,
            ),
        )?);
    }
    project_with(
        &project.clone(),
        Some(keywords(
            py,
            &[
                (
                    "effective_target_database",
                    or_else(
                        project.getattr("effective_target_database")?,
                        &defaults.default_database,
                    )?,
                ),
                (
                    "effective_target_schema",
                    or_else(
                        project.getattr("effective_target_schema")?,
                        &defaults.default_schema,
                    )?,
                ),
                ("models", PyTuple::new(py, models)?.into_any()),
                ("seeds", PyTuple::new(py, seeds)?.into_any()),
                ("functions", PyTuple::new(py, functions)?.into_any()),
            ],
        )?),
    )
}

/// `_resolve_target`: `target` with adapter defaults for a missing schema or database.
fn resolved_target<'py>(
    target: &Bound<'py, PyAny>,
    defaults: &TargetDefaults<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = target.py();
    let target_schema: Bound<'py, PyAny> = target.getattr("schema")?;
    let target_database: Bound<'py, PyAny> = target.getattr("database")?;
    let schema: Bound<'py, PyAny> = if target_schema.is_none() {
        defaults.default_schema.clone()
    } else {
        target_schema.clone()
    };
    let database: Bound<'py, PyAny> = if target_database.is_none() {
        defaults.default_database.clone()
    } else {
        target_database.clone()
    };
    let name: Bound<'py, PyAny> = target.getattr("name")?;
    let qualified_name: Bound<'py, PyAny> = call_with(
        &defaults.render_qualified_name,
        &[
            ("database", database.clone()),
            ("schema", schema.clone()),
            ("name", name.clone()),
        ],
    )?;
    if schema.eq(&target_schema)?
        && database.eq(&target_database)?
        && qualified_name.eq(target.getattr("qualified_name")?)?
    {
        return Ok(target.clone());
    }
    call_with(
        &registry::class(py, RecordId::CompiledRelationLocation)?,
        &[
            ("database", database),
            ("schema", schema),
            ("name", name),
            ("qualified_name", qualified_name),
            ("logical_schema", target.getattr("logical_schema")?),
            ("logical_database", target.getattr("logical_database")?),
        ],
    )
}
