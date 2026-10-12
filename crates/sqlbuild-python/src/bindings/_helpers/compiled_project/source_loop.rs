//! `build_source_inputs`: every discovered source attached natively into the compiled project.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use sqlbuild_analysis::assembly::project::models::{SyntaxCheck, SyntaxMode};
use sqlbuild_attachments::cursor_intrinsics::main::intrinsic_free::intrinsic_free;
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicCheck;
use sqlbuild_model_config::templates::models::TemplateOptions;

use crate::bindings::_helpers::compiled_project::model_loop::{
    LoopContext, NativeModelLoop, compile_error, record_reads,
};
use crate::bindings::_helpers::compiled_project::model_loop_host::ReferenceRow;
use crate::bindings::_helpers::compiled_project::model_loop_macros::{
    argument_references as macro_argument_references, expanded_with,
};
use crate::bindings::_helpers::compiled_project::source_views::{AttachedSource, replaced};
use crate::bindings::_helpers::model_config::config_errors::native_config_error;
use crate::bindings::_helpers::model_config::config_templates::{
    PythonHost, Stop, TemplateSources, expanded, template_error,
};
use crate::bindings::_helpers::project_assembly::resources::syntax_error_message;
use crate::bindings::_helpers::render::declaration_expansion::{
    DeclarationExpansion, ExpandedDeclarations, ExpansionClasses, ExpansionConsumer,
    expand_declarations,
};
use crate::bindings::_helpers::scopes::declaration_contexts::NativeDeclarationContexts;
use crate::bindings::_helpers::sqltext::declaration_references::declaration_scan;
use crate::bindings::_helpers::sqltext::static_sql::{InterpolationSources, interpolated};

const MACRO_TOKEN: char = '@';
const FILE_PATH_ARGUMENT: &str = "file_path";
const CONSTANT_TEXT_CALLBACK: &str = "constant_text";
const NATIVE_CONTEXTS_ATTRIBUTE: &str = "native_contexts";
const GENERIC_DIALECT: &str = "generic";
const EXPRESSION_STATEMENTS: [&str; 3] = ["select", "with", "values"];

/// One discovered source: its file's path, the discovered file and the entry.
pub(crate) type SourceRow = (String, Py<PyAny>, Py<PyAny>);

/// `(default contract, whether expressions are syntax-checked, source kind)`.
pub(crate) type SourceSettings = (Option<String>, bool, Py<PyAny>);

/// Attach every source in order, as `build_source_inputs` does.
pub(crate) fn attached_sources<'py>(
    model_loop: &NativeModelLoop,
    context: &LoopContext<'_, 'py>,
    rows: Vec<SourceRow>,
    settings: SourceSettings,
) -> PyResult<Vec<AttachedSource>> {
    let (default_contract, validate, source_kind) = settings;
    let py: Python<'py> = context.host.py();
    let source_kind: Bound<'py, PyAny> = source_kind.into_bound(py);
    let mut attached: Vec<AttachedSource> = Vec::with_capacity(rows.len());
    for (file_path, source_file, entry) in rows {
        let entry: Bound<'py, PyAny> = entry.into_bound(py);
        let name: String = entry.getattr("name")?.extract()?;
        let consumer: Bound<'py, PyAny> = context
            .classes
            .visibility
            .resource_identity
            .call1((&source_kind, &name))?;
        let declarations: Bound<'py, PyAny> = scoped_declarations(context, &file_path, &consumer)?;
        let (expression, usages) = match entry.getattr("expression")?.extract::<Option<String>>()? {
            Some(sql) => {
                let expansion: AuthoredExpansion<'py> =
                    expanded_authored_sql(context, (&sql, &file_path), &declarations)?;
                (Some(expansion.sql), expansion.usages)
            }
            None => (None, PyTuple::empty(py)),
        };
        let label = |field: &str| format!("source {name} {field}");
        let database: Option<String> =
            template_text(context, &entry, "database", &label("database"))?;
        let schema: Option<String> = template_text(context, &entry, "schema", &label("schema"))?;
        let table: Option<String> = template_text(context, &entry, "table", &label("table"))?;
        let description: Option<String> =
            template_text(context, &entry, "description", &label("description"))?;
        let meta: Bound<'py, PyAny> =
            template_value(context, &entry.getattr("meta")?, &label("meta"))?;
        let mut columns: Vec<Py<PyAny>> = Vec::new();
        for column in entry.getattr("columns")?.try_iter()? {
            columns.push(expanded_column(context, &name, &column?)?);
        }
        let mut audits: Vec<Py<PyAny>> = Vec::new();
        for audit in entry.getattr("audits")?.try_iter()? {
            let audit: Bound<'py, PyAny> = audit?;
            let definition: String = audit.getattr("definition_name")?.extract()?;
            audits.push(expanded_audit(
                context,
                &audit,
                &format!("source {name} audit {definition}"),
            )?);
        }
        if let Some(sql) = &expression {
            let label: String = format!("Source expression '{name}'");
            if let IntrinsicCheck::Rejected(message) =
                intrinsic_free(sql, &model_loop.reserved_markers, &label)
            {
                return Err(compile_error(context.classes, &message, None));
            }
            if validate {
                checked_expression(context, (&name, &file_path, sql))?;
            }
        }
        let contract: Option<String> = entry
            .getattr("contract")?
            .extract::<Option<String>>()?
            .or_else(|| default_contract.clone());
        attached.push(AttachedSource {
            source_file,
            entry: entry.unbind(),
            name,
            contract,
            database,
            schema,
            table,
            expression,
            description,
            meta: meta.unbind(),
            columns: PyTuple::new(py, columns)?.unbind(),
            audits: PyTuple::new(py, audits)?.unbind(),
            usages: usages.unbind(),
        });
    }
    Ok(attached)
}

/// A source's declaration context, or the public declarations when none are indexed.
pub(crate) fn scoped_declarations<'py>(
    context: &LoopContext<'_, 'py>,
    file_path: &str,
    consumer: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let visibility = &context.classes.visibility;
    if visibility.projects {
        let contexts: Bound<'py, NativeDeclarationContexts> = visibility
            .resolver
            .getattr(NATIVE_CONTEXTS_ATTRIBUTE)?
            .downcast_into()?;
        let (resolved, _) =
            contexts
                .get()
                .resolved_context(&visibility.resolver, file_path, Some(consumer))?;
        return Ok(resolved);
    }
    let fields: Bound<'py, PyDict> = PyDict::new(consumer.py());
    fields.set_item("enums", &visibility.public_enums)?;
    fields.set_item("constants", &visibility.public_constants)?;
    context
        .classes
        .macros
        .declaration_context
        .call((), Some(&fields))
}

/// Authored SQL after expansion, with its usages and typed macro argument references.
pub(crate) struct AuthoredExpansion<'py> {
    pub(crate) sql: String,
    pub(crate) usages: Bound<'py, PyTuple>,
    pub(crate) argument_references: Vec<ReferenceRow>,
}

/// `declaration_file_expansion`: a declaration file's folder context, consumed by `identity`.
pub(crate) fn file_declarations<'py>(
    context: &LoopContext<'_, 'py>,
    file_path: &str,
    identity: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let visibility = &context.classes.visibility;
    let py: Python<'py> = identity.py();
    let fields: Bound<'py, PyDict> = PyDict::new(py);
    fields.set_item("consumer", identity)?;
    if visibility.projects {
        let contexts: Bound<'py, NativeDeclarationContexts> = visibility
            .resolver
            .getattr(NATIVE_CONTEXTS_ATTRIBUTE)?
            .downcast_into()?;
        let (resolved, _) =
            contexts
                .get()
                .resolved_context(&visibility.resolver, file_path, None)?;
        return Ok(replaced(py, &resolved, &fields)?.into_bound(py));
    }
    fields.set_item("enums", &visibility.public_enums)?;
    fields.set_item("constants", &visibility.public_constants)?;
    context
        .classes
        .macros
        .declaration_context
        .call((), Some(&fields))
}

/// `expand_authored_sql_result`: interpolate, splice declarations and expand macros.
pub(crate) fn expanded_authored_sql<'py>(
    context: &LoopContext<'_, 'py>,
    authored: (&str, &str),
    declarations: &Bound<'py, PyAny>,
) -> PyResult<AuthoredExpansion<'py>> {
    let (sql, file_path) = authored;
    let py: Python<'py> = declarations.py();
    let hooks = &context.classes.sql_hooks;
    let (interpolated_sql, reads, error) = interpolated(
        InterpolationSources(
            hooks.effective_vars.clone(),
            hooks.environment.clone(),
            None,
            hooks.render_project_var.clone(),
        ),
        sql,
        file_path,
    )?;
    let reads: Vec<(String, String)> = reads
        .into_iter()
        .map(|(kind, name)| (kind.to_owned(), name))
        .collect();
    record_reads(context, &reads)?;
    if let Some(message) = error {
        return Err(compile_error(context.classes, &message, None));
    }
    let interpolated_sql: String = interpolated_sql.unwrap_or_else(|| sql.to_owned());
    let consumer: Bound<'py, PyAny> = declarations.getattr("consumer")?;
    let (references, stop) = declaration_scan(&interpolated_sql);
    let mut usages: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut argument_references: Vec<ReferenceRow> = Vec::new();
    let mut expanded_sql: String = interpolated_sql.clone();
    if !references.is_empty() || stop.is_some() {
        let file_keyword: Bound<'py, PyDict> = PyDict::new(py);
        file_keyword.set_item(
            FILE_PATH_ARGUMENT,
            context.classes.path_class.call1((file_path,))?,
        )?;
        let render_constant: Bound<'py, PyAny> = context.classes.partial.call(
            (context.host.getattr(CONSTANT_TEXT_CALLBACK)?,),
            Some(&file_keyword),
        )?;
        let classes: ExpansionClasses<'py> = ExpansionClasses {
            usage_record: context.classes.usage_record.clone(),
            compile_error: context.classes.compile_error.clone(),
        };
        let expanded: ExpandedDeclarations<'py> = expand_declarations(&DeclarationExpansion {
            sql: &interpolated_sql,
            references: &references,
            stop,
            context: declarations,
            consumer: ExpansionConsumer {
                identity: (!consumer.is_none()).then(|| consumer.clone()),
                relationship_visibility: false,
                path: file_path,
            },
            render_constant: &render_constant,
            classes: &classes,
        })?;
        expanded_sql = expanded.spliced.sql;
        usages.extend(expanded.usages);
    }
    if expanded_sql.contains(MACRO_TOKEN) {
        let resolver: &Bound<'py, PyAny> = &context.classes.visibility.resolver;
        let macro_declarations: Bound<'py, PyAny> = if resolver.is_none() {
            py.None().into_bound(py)
        } else {
            let contexts: Bound<'py, NativeDeclarationContexts> = resolver
                .getattr(NATIVE_CONTEXTS_ATTRIBUTE)?
                .downcast_into()?;
            contexts
                .get()
                .resolved_context(resolver, file_path, None)?
                .0
        };
        let output = expanded_with(
            context,
            (&macro_declarations, &consumer),
            file_path,
            &expanded_sql,
        )?;
        argument_references = macro_argument_references(context, &output)?;
        usages.extend(output.usages.into_iter().map(|usage| usage.into_bound(py)));
        expanded_sql = output.sql;
    }
    let unique: Bound<'py, PyDict> = PyDict::new(py);
    for usage in usages {
        unique.set_item(usage, py.None())?;
    }
    Ok(AuthoredExpansion {
        sql: expanded_sql,
        usages: PyTuple::new(py, unique.keys())?,
        argument_references,
    })
}

/// `_expand_source_template_value`: a text field with its `${...}` templates expanded.
fn template_text(
    context: &LoopContext<'_, '_>,
    owner: &Bound<'_, PyAny>,
    field: &str,
    label: &str,
) -> PyResult<Option<String>> {
    let raw: Bound<'_, PyAny> = owner.getattr(field)?;
    if raw.is_none() {
        return Ok(None);
    }
    Ok(Some(
        template_value(context, &raw, label)?.str()?.extract()?,
    ))
}

/// `_expand_source_template_object`: `${...}` templates expanded without context values.
fn template_value<'py>(
    context: &LoopContext<'_, 'py>,
    value: &Bound<'py, PyAny>,
    label: &str,
) -> PyResult<Bound<'py, PyAny>> {
    expanded_template(context, value, label, false)
}

/// `expand_config_templates` without context values; `preserve` keeps `@@CTX` tokens.
pub(crate) fn expanded_template<'py>(
    context: &LoopContext<'_, 'py>,
    value: &Bound<'py, PyAny>,
    label: &str,
    preserve: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = value.py();
    let hooks = &context.classes.sql_hooks;
    let host: PythonHost<'py> = PythonHost::new(
        py,
        TemplateSources(
            hooks.effective_vars.clone(),
            hooks.environment.clone(),
            PyDict::new(py),
        ),
        label,
    );
    let options: TemplateOptions = TemplateOptions {
        allow_context: false,
        preserve_context_tokens: preserve,
        preserve_unknown_context: false,
    };
    let result: Result<Bound<'py, PyAny>, Stop> = expanded(&host, value, options);
    let reads: Vec<(String, String)> = host
        .into_reads()
        .into_iter()
        .map(|(kind, name)| (kind.to_owned(), name))
        .collect();
    record_reads(context, &reads)?;
    match result {
        Ok(value) => Ok(value),
        Err(Stop::Python(error)) => Err(error),
        Err(Stop::Failure(error)) => {
            let error: Bound<'py, PyAny> = native_config_error(py, template_error(&error, label))?
                .into_bound(py)
                .into_any();
            Err(raised_config_error(context, &error))
        }
    }
}

fn raised_config_error(context: &LoopContext<'_, '_>, error: &Bound<'_, PyAny>) -> PyErr {
    let raised = (|| {
        let keywords: Bound<'_, PyDict> = PyDict::new(error.py());
        keywords.set_item("error", error)?;
        context.classes.config_error.call((), Some(&keywords))
    })();
    match raised {
        Ok(instance) => PyErr::from_value(instance),
        Err(failure) => failure,
    }
}

/// `expand_source_column_templates`.
fn expanded_column(
    context: &LoopContext<'_, '_>,
    source: &str,
    column: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let py: Python<'_> = column.py();
    let column_name: String = column.getattr("name")?.str()?.extract()?;
    let label = |field: &str| format!("source {source} column {column_name} {field}");
    let changes: Bound<'_, PyDict> = PyDict::new(py);
    changes.set_item(
        "type",
        template_text(context, column, "type", &label("type"))?,
    )?;
    changes.set_item(
        "description",
        template_text(context, column, "description", &label("description"))?,
    )?;
    changes.set_item(
        "meta",
        template_value(context, &column.getattr("meta")?, &label("meta"))?,
    )?;
    let mut audits: Vec<Py<PyAny>> = Vec::new();
    for audit in column.getattr("audits")?.try_iter()? {
        let audit: Bound<'_, PyAny> = audit?;
        let definition: String = audit.getattr("definition_name")?.extract()?;
        audits.push(expanded_audit(
            context,
            &audit,
            &label(&format!("audit {definition}")),
        )?);
    }
    changes.set_item("audits", PyTuple::new(py, audits)?)?;
    replaced_spec(column, &changes)
}

/// `expand_schema_audit_instance_templates`.
fn expanded_audit(
    context: &LoopContext<'_, '_>,
    audit: &Bound<'_, PyAny>,
    label: &str,
) -> PyResult<Py<PyAny>> {
    let changes: Bound<'_, PyDict> = PyDict::new(audit.py());
    changes.set_item(
        "arguments",
        template_value(
            context,
            &audit.getattr("arguments")?,
            &format!("{label} arguments"),
        )?,
    )?;
    changes.set_item(
        "description",
        template_text(
            context,
            audit,
            "description",
            &format!("{label} description"),
        )?,
    )?;
    replaced_spec(audit, &changes)
}

fn replaced_spec(value: &Bound<'_, PyAny>, changes: &Bound<'_, PyDict>) -> PyResult<Py<PyAny>> {
    replaced(value.py(), value, changes)
}

/// `validate_source_expression_syntax`: the expression parses as a FROM target.
fn checked_expression(context: &LoopContext<'_, '_>, source: (&str, &str, &str)) -> PyResult<()> {
    let (name, file_path, expression) = source;
    parse_checked(
        context,
        &format!("SELECT * FROM {}", expression_relation(expression)),
        &format!("SQL syntax error in source expression '{name}' ({file_path})"),
    )
}

/// `_validate_sql_syntax_with_message` for SQL a non-model resource owns.
pub(crate) fn parse_checked(
    context: &LoopContext<'_, '_>,
    sql: &str,
    error_prefix: &str,
) -> PyResult<()> {
    let py: Python<'_> = context.host.py();
    let check: SyntaxCheck = SyntaxCheck {
        sql: sql.to_owned(),
        placeholders: Vec::new(),
    };
    let Some(message) = syntax_error_message(py, &check, GENERIC_DIALECT, SyntaxMode::Parse)?
    else {
        return Ok(());
    };
    let keywords: Bound<'_, PyDict> = PyDict::new(py);
    keywords.set_item("help", &context.classes.source_syntax_help)?;
    let error: Bound<'_, PyAny> = context
        .classes
        .compile_error
        .call((format!("{error_prefix}: {message}"),), Some(&keywords))?;
    Err(PyErr::from_value(error))
}

/// `_render_source_expression_relation`: the expression as a table factor.
fn expression_relation(expression: &str) -> String {
    let trimmed: &str = str::trim(expression);
    let stripped: &str = str::trim(trimmed.strip_suffix(';').unwrap_or(trimmed));
    if stripped.starts_with('(') {
        return stripped.to_owned();
    }
    let lowered: String = stripped.to_lowercase();
    if EXPRESSION_STATEMENTS
        .iter()
        .any(|statement| lowered.starts_with(statement))
    {
        return format!("({stripped})");
    }
    stripped.to_owned()
}
