//! `build_project_audit_inputs`: singular and attached generic audits attached natively.

use std::collections::{BTreeMap, HashMap};

use pyo3::FromPyObject;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{
    PyBool, PyBoolMethods, PyDict, PyDictMethods, PyString, PyTuple, PyTupleMethods,
};
use sqlbuild_analysis::compiled_project::main::merge_call_site_references::merge_call_site_references;
use sqlbuild_attachments::audits::main::attached_model_reference_error::attached_model_reference_error;
use sqlbuild_attachments::audits::main::audit_reference_error::audit_reference_error;
use sqlbuild_attachments::audits::main::render_attached_audit::render_attached_audit;
use sqlbuild_attachments::audits::main::resolve_audit_policies::resolve_audit_policies;
use sqlbuild_attachments::audits::main::singular_audit_resources::singular_audit_resources;
use sqlbuild_attachments::audits::models::{
    AuditAttachment, AuditRendering, PolicySource, SingularAuditResources,
};
use sqlbuild_attachments::cursor_intrinsics::main::intrinsic_free::intrinsic_free;
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicCheck;
use sqlbuild_attachments::functions::models::KnownResources;
use sqlbuild_sqltext::sql_references::models::SqlReference;

use crate::bindings::_helpers::attachments::argument_values::argument_pairs;
use crate::bindings::_helpers::compiled_project::audit_views::{AttachedAudit, AttachedTarget};
use crate::bindings::_helpers::compiled_project::model_loop::{
    LoopContext, NativeModelLoop, compile_error, helped_compile_error,
};
use crate::bindings::_helpers::compiled_project::model_loop_calls::origin_references;
use crate::bindings::_helpers::compiled_project::model_loop_host::ReferenceRow;
use crate::bindings::_helpers::compiled_project::model_loop_inputs::reference_row;
use crate::bindings::_helpers::compiled_project::model_loop_named::{
    AUDIT_DECLARATION, resource_named_usages,
};
use crate::bindings::_helpers::compiled_project::source_loop::{
    AuthoredExpansion, expanded_authored_sql, file_declarations,
};
use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::model_config::header_metadata::thresholds;
use crate::bindings::_helpers::model_config::model_validator::NativeModelValidator;
use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::header_metadata::main::parse_measurement_policy::parse_measurement_policy;

const THRESHOLDS_KEY: &str = "thresholds";
const MINIMUM_SAMPLES_KEY: &str = "minimum_samples";
const MEASUREMENT_HEADER_KEYS: [&str; 2] = [THRESHOLDS_KEY, MINIMUM_SAMPLES_KEY];
const STANDALONE_MEASUREMENT_LABEL: &str = "standalone measurement audit";
const SEVERITY_KEY: &str = "severity";
const RUN_SCOPE_KEY: &str = "run_scope";
const ALWAYS_RUN_KEY: &str = "always_run";
const COLUMN_ARGUMENT: &str = "column";
const RELATION_ARGUMENT: &str = "relation";
const SINGULAR_AUDIT_CODE: &str = "P004";
const BUILT_IN_SHADOW_CODE: &str = "P003";
const AUDIT_RESOURCE_TYPE: &str = "audit";
const MODEL_TARGET: &str = "model";
const SOURCE_TARGET: &str = "source";
const SEED_TARGET: &str = "seed";

/// An audit block, its name, SQL body, evidence SQL, measurement flag and header values.
pub(crate) type AuditBlockRow = (
    Py<PyAny>,
    Option<String>,
    String,
    Option<String>,
    bool,
    Py<PyDict>,
);

/// An audit file's paths, stem, discovered file, generic flag, contents and blocks.
pub(crate) type AuditFileRow = (
    String,
    String,
    String,
    Py<PyAny>,
    bool,
    String,
    Vec<AuditBlockRow>,
);

/// What every audit in one compile resolves against, and the Python values it builds with.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct AuditSettings {
    default_severity: Option<String>,
    default_run_scope: Option<String>,
    /// Built-in generic definitions as audit file rows, overridden by project definitions.
    builtins: Vec<AuditFileRow>,
    /// `DeclarationIdentity`, and the singular and generic audit `DeclarationKind`s.
    declaration_identity: Py<PyAny>,
    singular_kind: Py<PyAny>,
    audit_kind: Py<PyAny>,
    /// `ResourceKind` by value, for the resources singular audits read and attach to.
    resource_kinds: Py<PyDict>,
}

/// Generic definitions by name, and the warnings for project ones overriding built-ins.
type Definitions<'a, 'py> = (HashMap<String, Definition<'a>>, Vec<Bound<'py, PyAny>>);

/// One generic definition: its file row and its only block.
struct Definition<'a> {
    file: &'a AuditFileRow,
    block: &'a AuditBlockRow,
}

/// One resource's attached audits: its target, consumer path, and owner files and instances.
pub(crate) struct AttachmentOwner<'py> {
    pub(crate) kind: &'static str,
    pub(crate) name: String,
    pub(crate) relation: String,
    pub(crate) path: String,
    /// `(owner file, column, instance)` in attachment order.
    pub(crate) instances: Vec<(String, Option<String>, Bound<'py, PyAny>)>,
}

/// Every singular audit, then each owner's attached audits, and the built-in shadow warnings.
pub(crate) fn attached_audits<'py>(
    model_loop: &NativeModelLoop,
    context: &LoopContext<'_, 'py>,
    inputs: (&[AuditFileRow], Vec<AttachmentOwner<'py>>),
    settings: &AuditSettings,
) -> PyResult<(Vec<AttachedAudit>, Vec<Bound<'py, PyAny>>)> {
    let (files, owners) = inputs;
    let (definitions, shadows) = generic_definitions(context, files, &settings.builtins)?;
    let scope = AuditScope {
        model_loop,
        context,
        settings,
    };
    let mut audits: Vec<AttachedAudit> = Vec::new();
    for file in files.iter().filter(|file| !file.4) {
        for block in &file.6 {
            audits.push(scope.singular(file, block)?);
        }
    }
    for owner in &owners {
        for (owner_file, column, instance) in &owner.instances {
            audits.push(scope.attached(
                &definitions,
                owner,
                (owner_file, column.as_deref()),
                instance,
            )?);
        }
    }
    Ok((audits, shadows))
}

/// `index_generic_audit_definitions` merged over the built-ins, with P003 for each override.
fn generic_definitions<'a, 'py>(
    context: &LoopContext<'_, 'py>,
    files: &'a [AuditFileRow],
    builtins: &'a [AuditFileRow],
) -> PyResult<Definitions<'a, 'py>> {
    let py: Python<'py> = context.host.py();
    let mut project: BTreeMap<String, Definition<'a>> = BTreeMap::new();
    for file in files.iter().filter(|file| file.4) {
        let [block] = file.6.as_slice() else {
            let message: String = format!(
                "Generic audit definition {} must contain exactly one AUDIT block",
                file.1
            );
            return Err(compile_error(context.classes, &message, None));
        };
        let header: &Bound<'_, PyDict> = block.5.bind(py);
        if block.4
            && (header.contains(MEASUREMENT_HEADER_KEYS[0])?
                || header.contains(MEASUREMENT_HEADER_KEYS[1])?)
        {
            let message: String = format!(
                "Generic measurement audit definition {} must not define thresholds or \
                 minimum_samples in its AUDIT header; attachment owns policy",
                file.1
            );
            return Err(compile_error(context.classes, &message, None));
        }
        if let Some(existing) = project.get(&file.2) {
            let message: String = format!(
                "Duplicate generic audit definition found for '{}' in {} and {}",
                file.2, existing.file.1, file.1
            );
            return Err(compile_error(context.classes, &message, None));
        }
        project.insert(file.2.clone(), Definition { file, block });
    }
    let mut shadows: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut definitions: HashMap<String, Definition<'a>> = HashMap::new();
    for builtin in builtins {
        if let Some(block) = builtin.6.first() {
            definitions.insert(
                builtin.2.clone(),
                Definition {
                    file: builtin,
                    block,
                },
            );
        }
    }
    for (name, definition) in project {
        if definitions.contains_key(&name) {
            shadows.push(shadow_warning(context, &name, &definition.file.1)?);
        }
        definitions.insert(name, definition);
    }
    Ok((definitions, shadows))
}

/// The P003 warning for a project audit that overrides a built-in one.
fn shadow_warning<'py>(
    context: &LoopContext<'_, 'py>,
    name: &str,
    relative_path: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.host.py();
    let fields: Bound<'py, PyDict> = PyDict::new(py);
    fields.set_item("phase", "compile")?;
    fields.set_item("severity", "warning")?;
    fields.set_item("code", BUILT_IN_SHADOW_CODE)?;
    fields.set_item(
        "message",
        format!("project audit '{name}' overrides built-in audit '{name}'"),
    )?;
    fields.set_item("path", context.classes.path_class.call1((relative_path,))?)?;
    fields.set_item(
        "help",
        "rename the project audit if this override is unintended",
    )?;
    context.classes.compiler_diagnostic.call((), Some(&fields))
}

/// The loop, its context and the settings each audit is attached with.
struct AuditScope<'a, 'py> {
    model_loop: &'a NativeModelLoop,
    context: &'a LoopContext<'a, 'py>,
    settings: &'a AuditSettings,
}

/// An audit's expanded SQL bodies, references and usages.
struct ExpandedAudit<'py> {
    sql_body: String,
    evidence_sql: Option<String>,
    references: Vec<ReferenceRow>,
    usages: Vec<Bound<'py, PyAny>>,
}

impl<'py> AuditScope<'_, 'py> {
    /// One singular audit block, as `_build_singular_audit_inputs` builds it.
    fn singular(&self, file: &AuditFileRow, block: &AuditBlockRow) -> PyResult<AttachedAudit> {
        let py: Python<'py> = self.context.host.py();
        let (_, relative_path, stem, audit_file, _, _, _) = file;
        let (audit_block, block_name, sql_body, evidence_sql, measurement, header) = block;
        let audit_name: String = block_name.clone().unwrap_or_else(|| stem.clone());
        let identity: Bound<'py, PyAny> = self
            .settings
            .declaration_identity
            .bind(py)
            .call1((self.settings.singular_kind.bind(py), &audit_name))?;
        let label: String = format!("Audit '{audit_name}'");
        let expanded: ExpandedAudit<'py> =
            self.expanded(file, (sql_body, evidence_sql.as_deref()), &identity, &label)?;
        let calls: Vec<(&str, &str)> = reference_calls(&expanded.references);
        self.checked_references(relative_path, &calls)?;
        let resources: SingularAuditResources = singular_audit_resources(&calls);
        if let Some((message, help)) = &resources.problem {
            self.report_not_cross_resource(relative_path, &audit_name, (message, help))?;
        }
        let header: &Bound<'py, PyDict> = header.bind(py);
        let severity: Option<String> = header_text(header, SEVERITY_KEY)?;
        let run_scope: Option<String> = header_text(header, RUN_SCOPE_KEY)?;
        let always_run: bool = match header.get_item(ALWAYS_RUN_KEY)? {
            Some(value) => value.downcast::<PyBool>().is_ok_and(|flag| flag.is_true()),
            None => false,
        };
        let (thresholds, minimum_samples) = self.measurement_policy(header, relative_path)?;
        let (severity, run_scope) = if *measurement {
            if severity.is_some() {
                let message: String = format!(
                    "{relative_path}: measurement audits must not define severity; severity \
                     derives from thresholds"
                );
                return Err(compile_error(self.context.classes, &message, None));
            }
            if thresholds.is_none() {
                let message: String = format!(
                    "{relative_path}: standalone measurement audit must define thresholds in its \
                     AUDIT header"
                );
                return Err(compile_error(self.context.classes, &message, None));
            }
            let severity: &'static str = if thresholds.getattr("error")?.is_none() {
                "warn"
            } else {
                "error"
            };
            (
                severity,
                self.policies(None, relative_path, run_scope.as_deref())?.1,
            )
        } else {
            self.policies(
                Some(severity.as_deref()),
                relative_path,
                run_scope.as_deref(),
            )?
        };
        let mut usages: Vec<Bound<'py, PyAny>> = expanded.usages;
        let resource_kinds: &Bound<'py, PyDict> = self.settings.resource_kinds.bind(py);
        for (kind, name) in &resources.resources {
            let kind: Bound<'py, PyAny> = resource_kinds
                .get_item(kind)?
                .ok_or_else(|| compile_error(self.context.classes, kind, None))?;
            let resource: Bound<'py, PyAny> = self
                .context
                .classes
                .visibility
                .resource_identity
                .call1((kind, name))?;
            let fields: Bound<'py, PyDict> = PyDict::new(py);
            fields.set_item("consumer", resource)?;
            fields.set_item("declaration", &identity)?;
            usages.push(self.context.classes.usage_record.call((), Some(&fields))?);
        }
        Ok(AttachedAudit {
            audit_file: audit_file.clone_ref(py),
            audit_block: audit_block.clone_ref(py),
            definition_name: audit_name,
            sql_body: expanded.sql_body,
            measurement: *measurement,
            evidence_sql: expanded.evidence_sql,
            thresholds: thresholds.unbind(),
            minimum_samples: minimum_samples.unbind(),
            evidence_limit: py.None(),
            references: expanded.references,
            target: None,
            severity,
            run_scope,
            always_run,
            usages: PyTuple::new(py, usages)?.unbind(),
            name: None,
            description: None,
        })
    }

    /// One attached generic audit instance, as `build_attached_audit_input` builds it.
    fn attached(
        &self,
        definitions: &HashMap<String, Definition<'_>>,
        owner: &AttachmentOwner<'py>,
        attachment: (&str, Option<&str>),
        instance: &Bound<'py, PyAny>,
    ) -> PyResult<AttachedAudit> {
        let py: Python<'py> = self.context.host.py();
        let (owner_file, column) = attachment;
        let definition_name: String = instance.getattr("definition_name")?.extract()?;
        let Some(definition) = definitions.get(&definition_name) else {
            let message: String =
                format!("{owner_file} references unknown generic audit '{definition_name}'");
            return Err(compile_error(self.context.classes, &message, None));
        };
        let consumer: Bound<'py, PyAny> =
            self.context.classes.visibility.resource_identity.call1((
                self.settings.resource_kinds.bind(py).get_item(owner.kind)?,
                &owner.name,
            ))?;
        let mut usages: Vec<Bound<'py, PyAny>> = resource_named_usages(
            self.context,
            (&AUDIT_DECLARATION, &definition_name),
            &consumer,
            (owner.kind, &owner.name, &owner.path),
        )?;
        let thresholds: Bound<'py, PyAny> = instance.getattr("thresholds")?;
        let minimum_samples: Bound<'py, PyAny> = instance.getattr("minimum_samples")?;
        let instance_severity: Option<String> = instance.getattr("severity")?.extract()?;
        let label: String = format!("{owner_file} audit '{definition_name}'");
        let measurement: bool = definition.block.4;
        if measurement {
            if instance_severity.is_some() {
                let message: String = format!(
                    "{label}: measurement audit attachments must not define severity; severity \
                     derives from thresholds"
                );
                return Err(compile_error(self.context.classes, &message, None));
            }
            if thresholds.is_none() {
                let message: String = format!(
                    "{label}: measurement audit attachments must define at least one threshold"
                );
                return Err(compile_error(self.context.classes, &message, None));
            }
        } else if !thresholds.is_none() || !minimum_samples.is_none() {
            let message: String = format!(
                "{label}: thresholds and minimum_samples are only valid for measurement audits"
            );
            return Err(compile_error(self.context.classes, &message, None));
        }
        let mut implicit: Vec<(String, String)> = vec![
            (owner.kind.to_owned(), owner.name.clone()),
            (RELATION_ARGUMENT.to_owned(), owner.relation.clone()),
        ];
        if let Some(column) = column {
            implicit.push((COLUMN_ARGUMENT.to_owned(), column.to_owned()));
        }
        let rendering: AuditRendering = render_attached_audit(&AuditAttachment {
            owner_label: owner_file.to_owned(),
            definition_name: definition_name.clone(),
            sql_body: definition.block.2.clone(),
            evidence_sql: definition.block.3.clone(),
            implicit_arguments: implicit,
            explicit_arguments: argument_pairs(instance.getattr("arguments")?.downcast()?)?,
            has_thresholds: !thresholds.is_none(),
            threshold_error: !thresholds.is_none() && !thresholds.getattr("error")?.is_none(),
            instance_severity,
            default_severity: self.settings.default_severity.clone(),
            instance_run_scope: instance.getattr("run_scope")?.extract()?,
            default_run_scope: self.settings.default_run_scope.clone(),
        });
        let rendered = match rendering {
            AuditRendering::Failed(message) => {
                return Err(compile_error(self.context.classes, &message, None));
            }
            AuditRendering::Rendered(rendered) => rendered,
        };
        let identity: Bound<'py, PyAny> = self
            .settings
            .declaration_identity
            .bind(py)
            .call1((self.settings.audit_kind.bind(py), &definition_name))?;
        let expanded: ExpandedAudit<'py> = self.expanded(
            definition.file,
            (&rendered.sql_body, rendered.evidence_sql.as_deref()),
            &identity,
            &format!("Audit '{definition_name}'"),
        )?;
        let calls: Vec<(&str, &str)> = reference_calls(&expanded.references);
        self.checked_references(&definition.file.1, &calls)?;
        let (severity, source) = rendered
            .policies
            .map_err(|message| compile_error(self.context.classes, &message, None))?;
        let run_scope: String = match source {
            PolicySource::Instance => instance.getattr("run_scope")?.extract()?,
            PolicySource::Default => self.settings.default_run_scope.clone().unwrap_or_default(),
            PolicySource::Fallback => "delta_and_final".to_owned(),
        };
        if let Some(message) =
            attached_model_reference_error(&label, (owner.kind, &owner.name), &calls)
        {
            return Err(compile_error(self.context.classes, &message, None));
        }
        usages.extend(expanded.usages);
        Ok(AttachedAudit {
            audit_file: definition.file.3.clone_ref(py),
            audit_block: definition.block.0.clone_ref(py),
            definition_name: definition
                .block
                .1
                .clone()
                .unwrap_or_else(|| definition.file.2.clone()),
            sql_body: expanded.sql_body,
            measurement,
            evidence_sql: expanded.evidence_sql,
            thresholds: thresholds.unbind(),
            minimum_samples: minimum_samples.unbind(),
            evidence_limit: instance.getattr("evidence_limit")?.unbind(),
            references: expanded.references,
            target: Some(AttachedTarget {
                kind: owner.kind.to_owned(),
                name: owner.name.clone(),
                column: column.map(str::to_owned),
            }),
            severity,
            run_scope,
            always_run: instance.getattr(ALWAYS_RUN_KEY)?.is_truthy()?,
            usages: PyTuple::new(py, usages)?.unbind(),
            name: instance.getattr("name")?.extract()?,
            description: instance.getattr("description")?.extract()?,
        })
    }

    /// Body and evidence expanded in `file`'s scope, intrinsic-free, with their references.
    fn expanded(
        &self,
        file: &AuditFileRow,
        sql: (&str, Option<&str>),
        identity: &Bound<'py, PyAny>,
        label: &str,
    ) -> PyResult<ExpandedAudit<'py>> {
        let (file_path, relative_path, _, _, _, contents, _) = file;
        let declarations: Bound<'py, PyAny> = file_declarations(self.context, file_path, identity)?;
        let body: AuthoredExpansion<'py> = expanded_authored_sql(
            self.model_loop,
            self.context,
            (sql.0, file_path),
            &declarations,
        )?;
        let evidence: Option<AuthoredExpansion<'py>> = sql
            .1
            .map(|evidence| {
                expanded_authored_sql(
                    self.model_loop,
                    self.context,
                    (evidence, file_path),
                    &declarations,
                )
            })
            .transpose()?;
        self.intrinsic_free(&body.sql, label)?;
        if let Some(evidence) = &evidence {
            self.intrinsic_free(&evidence.sql, &format!("{label} evidence"))?;
        }
        let mut scanned: Vec<ReferenceRow> =
            self.references(&body.sql, (file_path, relative_path, contents))?;
        let mut arguments: Vec<ReferenceRow> = body.argument_references;
        let mut usages: Vec<Bound<'py, PyAny>> = body.usages.iter().collect();
        if let Some(evidence) = &evidence {
            for row in self.references(&evidence.sql, (file_path, relative_path, contents))? {
                if !scanned.contains(&row) {
                    scanned.push(row);
                }
            }
            arguments.extend(evidence.argument_references.iter().cloned());
            usages.extend(evidence.usages.iter());
        }
        Ok(ExpandedAudit {
            sql_body: body.sql,
            evidence_sql: evidence.map(|evidence| evidence.sql),
            references: merge_call_site_references(scanned, arguments),
            usages,
        })
    }

    fn intrinsic_free(&self, sql: &str, label: &str) -> PyResult<()> {
        match intrinsic_free(
            self.model_loop.python,
            sql,
            &self.model_loop.reserved_markers,
            label,
        ) {
            IntrinsicCheck::Free => Ok(()),
            IntrinsicCheck::Rejected(message) => {
                Err(compile_error(self.context.classes, &message, None))
            }
        }
    }

    /// One SQL text's references, reporting rejected calls against the audit file.
    fn references(&self, sql: &str, file: (&str, &str, &str)) -> PyResult<Vec<ReferenceRow>> {
        let references: Vec<SqlReference> =
            origin_references(self.context, &self.model_loop.syntax, sql, file)?;
        let mut rows: Vec<ReferenceRow> = Vec::with_capacity(references.len());
        for row in references.iter().map(reference_row) {
            if !rows.contains(&row) {
                rows.push(row);
            }
        }
        Ok(rows)
    }

    /// `validate_audit_references` against the project's discovered resources.
    fn checked_references(&self, relative_path: &str, calls: &[(&str, &str)]) -> PyResult<()> {
        let validator: Bound<'_, NativeModelValidator> = self
            .model_loop
            .validator
            .bind(self.context.host.py())
            .downcast()?
            .clone();
        let known: KnownResources<'_> = validator.get().known_resources();
        match audit_reference_error(relative_path, calls, &known) {
            Some(message) => Err(compile_error(self.context.classes, &message, None)),
            None => Ok(()),
        }
    }

    /// The header's `MeasurementThresholds` and authored `minimum_samples`, as Python parses them.
    fn measurement_policy(
        &self,
        header: &Bound<'py, PyDict>,
        relative_path: &str,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
        let py: Python<'py> = header.py();
        let raw =
            |key: &str| -> PyResult<Option<PyNode<'py>>> { Ok(header.get_item(key)?.map(PyNode)) };
        let (thresholds_node, samples_node) = (raw(THRESHOLDS_KEY)?, raw(MINIMUM_SAMPLES_KEY)?);
        let (parsed, minimum_samples) = parse_measurement_policy(
            (thresholds_node.as_ref(), samples_node.as_ref()),
            relative_path,
            STANDALONE_MEASUREMENT_LABEL,
        )
        .map_err(|error| self.config_error(&error))?;
        Ok((
            thresholds(py, self.context.contracts, parsed.as_ref())?,
            minimum_samples.map_or_else(|| py.None().into_bound(py), |node| node.0),
        ))
    }

    /// `CompileInputError` with `error`'s message and help.
    fn config_error(&self, error: &ConfigError) -> PyErr {
        helped_compile_error(self.context.classes, &error.message, error.help.as_deref())
    }

    /// The resolved severity and run scope; a measurement (`None`) severity reads no default.
    fn policies(
        &self,
        severity: Option<Option<&str>>,
        label: &str,
        run_scope: Option<&str>,
    ) -> PyResult<(&'static str, String)> {
        let (instance, default) = match severity {
            Some(instance) => (instance, self.settings.default_severity.as_deref()),
            None => (None, None),
        };
        resolve_audit_policies(
            (instance, default, label),
            (run_scope, self.settings.default_run_scope.as_deref()),
        )
        .map_err(|message| compile_error(self.context.classes, &message, None))
    }

    /// Report P004 for a singular audit that does not read two resources.
    fn report_not_cross_resource(
        &self,
        relative_path: &str,
        audit_name: &str,
        problem: (&str, &str),
    ) -> PyResult<()> {
        let py: Python<'py> = self.context.host.py();
        let (message, help) = problem;
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        fields.set_item("phase", "compile")?;
        fields.set_item("severity", "error")?;
        fields.set_item("code", SINGULAR_AUDIT_CODE)?;
        fields.set_item(
            "message",
            format!("Singular audit '{audit_name}' in {relative_path} {message}"),
        )?;
        fields.set_item("resource_type", AUDIT_RESOURCE_TYPE)?;
        fields.set_item("resource_name", audit_name)?;
        fields.set_item(
            "path",
            self.context.classes.path_class.call1((relative_path,))?,
        )?;
        fields.set_item("help", help)?;
        let diagnostic: Bound<'py, PyAny> = self
            .context
            .classes
            .compiler_diagnostic
            .call((), Some(&fields))?;
        let key: Bound<'py, PyTuple> = PyTuple::new(
            py,
            [
                SINGULAR_AUDIT_CODE,
                &relative_path.replace('\\', "/"),
                audit_name,
            ],
        )?;
        let arguments: Bound<'py, PyDict> = PyDict::new(py);
        arguments.set_item("key", key)?;
        arguments.set_item("diagnostic", diagnostic)?;
        self.context
            .classes
            .report_diagnostic
            .call((), Some(&arguments))?;
        Ok(())
    }
}

fn reference_calls(references: &[ReferenceRow]) -> Vec<(&str, &str)> {
    references
        .iter()
        .map(|(kind, name, _, _)| (kind.as_str(), name.as_str()))
        .collect()
}

/// `_str_from_dict`: a header value when it is a string.
fn header_text(header: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    match header.get_item(key)? {
        Some(value) if value.is_instance_of::<PyString>() => Ok(Some(value.extract()?)),
        _ => Ok(None),
    }
}

/// The attachment owners of every model, source and seed, as the audit loop reads them.
pub(crate) fn model_owner<'py>(
    name: String,
    path: String,
    schema: (&Bound<'py, PyTuple>, &Bound<'py, PyTuple>),
) -> PyResult<AttachmentOwner<'py>> {
    let (audits, columns) = schema;
    let mut instances: Vec<(String, Option<String>, Bound<'py, PyAny>)> = Vec::new();
    for audit in audits.iter() {
        instances.push((path.clone(), explicit_column(&audit)?, audit));
    }
    for column in columns.iter() {
        let column_owner: String = location_path(&column)?.unwrap_or_else(|| path.clone());
        let column_name: String = column.getattr("name")?.extract()?;
        for audit in column.getattr("audits")?.try_iter()? {
            let audit: Bound<'py, PyAny> = audit?;
            let owner_file: String = location_path(&audit)?.unwrap_or_else(|| column_owner.clone());
            instances.push((owner_file, Some(column_name.clone()), audit));
        }
    }
    Ok(AttachmentOwner {
        kind: MODEL_TARGET,
        relation: format!("__ref(\"{}\")", name.replace('"', "\"\"")),
        name,
        path,
        instances,
    })
}

/// A source's or seed's attachment owner; source table audits name no explicit column.
pub(crate) fn resource_owner<'py>(
    kind: &'static str,
    name: String,
    paths: (String, String),
    schema: (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<AttachmentOwner<'py>> {
    let (path, owner_file) = paths;
    let (audits, columns) = schema;
    let mut instances: Vec<(String, Option<String>, Bound<'py, PyAny>)> = Vec::new();
    for audit in audits.try_iter()? {
        let audit: Bound<'py, PyAny> = audit?;
        let column: Option<String> = if kind == SEED_TARGET {
            explicit_column(&audit)?
        } else {
            None
        };
        instances.push((owner_file.clone(), column, audit));
    }
    for column in columns.try_iter()? {
        let column: Bound<'py, PyAny> = column?;
        let column_name: String = column.getattr("name")?.extract()?;
        for audit in column.getattr("audits")?.try_iter()? {
            instances.push((owner_file.clone(), Some(column_name.clone()), audit?));
        }
    }
    let function: &str = if kind == SOURCE_TARGET {
        "__source"
    } else {
        "__seed"
    };
    Ok(AttachmentOwner {
        kind,
        relation: format!("{function}(\"{}\")", name.replace('"', "\"\"")),
        name,
        path,
        instances,
    })
}

/// `_explicit_audit_column_name`: the instance's `column` argument when it is a string.
fn explicit_column(audit: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    let arguments: Bound<'_, PyDict> = audit.getattr("arguments")?.downcast_into()?;
    header_text(&arguments, COLUMN_ARGUMENT)
}

/// The path of a spec's authored location, if it has one.
fn location_path(spec: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    let location: Bound<'_, PyAny> = spec.getattr("location")?;
    if location.is_none() {
        return Ok(None);
    }
    Ok(Some(location.getattr("path")?.str()?.to_string()))
}
