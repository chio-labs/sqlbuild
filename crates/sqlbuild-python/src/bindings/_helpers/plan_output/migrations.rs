//! Convert public migration models at the Python boundary for native presentation.

use crate::bindings::_helpers::plan_output::plan_text::display_limit;
use crate::bindings::_helpers::plan_output::values::{
    iso, items, optional_text, relation_name, text, texts,
};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cli_text::models::{
    CliStyle, ColumnMigrationText, MigrationDecisionText, MigrationText, MigrationTextReport,
    OldNameText, PreBuildWorkText, RetentionText, TableTypeText,
};
use sqlbuild_core::plan_display::main::{
    format_model_migrations, format_pre_build_work, old_name_rows,
};
use std::collections::BTreeMap;

fn label(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    text(&value.getattr("label")?).map(Some)
}

fn decision(entry: &Bound<'_, PyAny>) -> PyResult<MigrationDecisionText> {
    let value = entry.getattr("decision")?;
    Ok(MigrationDecisionText {
        value: text(&value)?,
        label: text(&value.getattr("label")?)?,
        blocks_build: entry.getattr("blocks_build")?.extract()?,
        origin_missing: entry.getattr("origin_missing")?.extract()?,
        ..MigrationDecisionText::default()
    })
}

fn migration(entry: &Bound<'_, PyAny>, materialization: Option<String>) -> PyResult<MigrationText> {
    let mut decision = decision(entry)?;
    let value = entry.getattr("decision")?;
    decision.decision_blocks_build = value.getattr("blocks_build")?.extract()?;
    decision.checks_compatibility = value.getattr("checks_compatibility")?.extract()?;
    Ok(MigrationText {
        model_name: text(&entry.getattr("model_name")?)?,
        origin: text(&relation_name(&entry.getattr("origin")?)?)?,
        destination: text(&relation_name(&entry.getattr("destination")?)?)?,
        decision,
        compatibility: text(&entry.getattr("compatibility")?.getattr("value")?)?,
        discovery: text(&entry.getattr("discovery")?.getattr("value")?)?,
        completed_at: optional_text(&iso(&entry.getattr("completed_at")?)?)?,
        target_label: text(&entry.getattr("target_label")?)?,
        transfer: label(&entry.getattr("transfer")?)?,
        transfer_fallback: label(&entry.getattr("transfer_fallback")?)?,
        storage_transition: optional_text(&entry.getattr("storage_transition")?)?,
        promotion: label(&entry.getattr("promotion")?)?,
        findings: texts(&entry.getattr("compatibility_findings")?)?,
        materialization,
    })
}

fn old_name(entry: &Bound<'_, PyAny>) -> PyResult<OldNameText> {
    let expires = entry.getattr("expires_at")?;
    let expires_date = if expires.is_none() {
        None
    } else {
        Some(expires.call_method1("strftime", ("%Y-%m-%d",))?.extract()?)
    };
    Ok(OldNameText {
        model_name: text(&entry.getattr("model_name")?)?,
        origin: text(&relation_name(&entry.getattr("origin")?)?)?,
        destination: text(&relation_name(&entry.getattr("destination")?)?)?,
        action: text(&entry.getattr("action")?)?,
        expires_date,
        column_aliases: entry.getattr("column_aliases")?.extract()?,
        grants_supported: entry.getattr("grants_supported")?.extract()?,
        grants_copied: optional_text(&entry.getattr("grants_copied")?)?,
        reason: optional_text(&entry.getattr("reason")?)?,
    })
}

fn column(entry: &Bound<'_, PyAny>) -> PyResult<ColumnMigrationText> {
    Ok(ColumnMigrationText {
        model_name: text(&entry.getattr("model_name")?)?,
        origin_column: text(&entry.getattr("origin_column")?)?,
        destination_column: text(&entry.getattr("destination_column")?)?,
        decision: decision(entry)?,
        discovery: text(&entry.getattr("discovery")?.getattr("value")?)?,
        completed_at: optional_text(&iso(&entry.getattr("completed_at")?)?)?,
    })
}

/// Migration sections appended to `lines`, in planner order.
pub(crate) fn migration_lines(
    lines: Vec<String>,
    plan: &Bound<'_, PyAny>,
    display_options: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    let mut materializations: BTreeMap<String, String> = BTreeMap::new();
    for entry in items(&plan.getattr("model_entries")?)? {
        materializations.insert(
            text(&entry.getattr("name")?)?,
            text(&entry.getattr("materialization_type")?)?,
        );
    }
    let mut migrations: Vec<MigrationText> = Vec::new();
    for entry in items(&plan.getattr("migration_entries")?)? {
        let name = text(&entry.getattr("model_name")?)?;
        migrations.push(migration(&entry, materializations.get(&name).cloned())?);
    }
    let report = MigrationTextReport {
        migrations,
        old_names: items(&plan.getattr("old_name_view_entries")?)?
            .iter()
            .map(old_name)
            .collect::<PyResult<_>>()?,
        columns: items(&plan.getattr("column_migration_entries")?)?
            .iter()
            .map(column)
            .collect::<PyResult<_>>()?,
        display: display_limit(display_options)?,
        manual_rename_hint: plan
            .py()
            .import("sqlbuild.compiler.planner.constants")?
            .getattr("MANUAL_RENAME_HINT")?
            .extract()?,
    };
    Ok(format_model_migrations::format_model_migrations(
        lines, &report,
    ))
}

#[pyfunction(name = "format_model_migrations", signature = (*, lines, plan, display_options))]
fn format_migrations(
    lines: Vec<String>,
    plan: &Bound<'_, PyAny>,
    display_options: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    migration_lines(lines, plan, display_options)
}

fn days(value: &Bound<'_, PyAny>) -> PyResult<Option<i64>> {
    value.extract()
}

/// Table-type, retention and migration work that runs before model builds.
pub(crate) fn pre_build_lines(
    lines: Vec<String>,
    plan: &Bound<'_, PyAny>,
    display_options: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    let mut table_types: Vec<TableTypeText> = Vec::new();
    for entry in items(&plan.getattr("table_type_entries")?)? {
        table_types.push(TableTypeText {
            model_name: text(&entry.getattr("model_name")?)?,
            desired_type: text(&entry.getattr("desired_type")?)?,
            actual_type: optional_text(&entry.getattr("actual_type")?)?
                .filter(|actual| !actual.is_empty()),
            source: text(&entry.getattr("source")?)?,
            irreversible_warning: optional_text(&entry.getattr("irreversible_warning")?)?,
        });
    }
    let mut retention: Vec<RetentionText> = Vec::new();
    for entry in items(&plan.getattr("retention_entries")?)? {
        let request = entry.getattr("request")?;
        let mut parts: Vec<String> = Vec::new();
        for field in ["database", "schema", "name"] {
            let part = request.getattr(field)?;
            if part.is_truthy()? {
                parts.push(text(&part)?);
            }
        }
        retention.push(RetentionText {
            scope: parts.join("."),
            desired_days: request.getattr("desired_days")?.extract()?,
            actual_days: days(&entry.getattr("actual_days")?)?,
            effective_days: days(&entry.getattr("effective_days")?)?,
            source: text(&entry.getattr("source")?)?,
            direction: text(&entry.getattr("direction")?.getattr("value")?)?,
            phase: text(&entry.getattr("phase")?.getattr("value")?)?,
            irreversible_warning: optional_text(&entry.getattr("irreversible_warning")?)?,
        });
    }
    let work = PreBuildWorkText {
        table_types,
        retention,
        display: display_limit(display_options)?,
    };
    migration_lines(
        format_pre_build_work::format_pre_build_work(lines, &work),
        plan,
        display_options,
    )
}

/// Format retention, table-type, and migration work that runs before model builds.
#[pyfunction(name = "format_pre_build_work", signature = (*, lines, plan, display_options))]
fn format_pre_build(
    lines: Vec<String>,
    plan: &Bound<'_, PyAny>,
    display_options: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    pre_build_lines(lines, plan, display_options)
}

#[pyfunction(name = "old_name_rows", signature = (*, entry, style))]
fn render_old_name(entry: &Bound<'_, PyAny>, style: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    Ok(old_name_rows::old_name_rows(
        &old_name(entry)?,
        CliStyle {
            use_color: style.getattr("use_color")?.extract()?,
        },
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(format_migrations, module)?)?;
    module.add_function(wrap_pyfunction!(format_pre_build, module)?)?;
    module.add_function(wrap_pyfunction!(render_old_name, module)?)
}
