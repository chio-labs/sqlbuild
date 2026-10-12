//! The compile-input model loop: each model's steps run in the attachment's order, natively.

use crate::bindings::_helpers::compiled_project::audit_loop::{
    AttachmentOwner, AuditFileRow, AuditSettings, attached_audits,
};
use crate::bindings::_helpers::compiled_project::audit_views::AttachedAudit;
use crate::bindings::_helpers::compiled_project::function_loop::{
    FunctionRow, FunctionSettings, attached_functions, checked_table_function_arities,
};
use crate::bindings::_helpers::compiled_project::function_views::AttachedFunction;
use crate::bindings::_helpers::compiled_project::model_input_view::NativeModelInput;
use crate::bindings::_helpers::compiled_project::model_loop_calls::report_invalid_calls;
use crate::bindings::_helpers::compiled_project::model_loop_config::{ConfigClasses, ModelConfigs};
use crate::bindings::_helpers::compiled_project::model_loop_external::external_errors;
use crate::bindings::_helpers::compiled_project::model_loop_header::{
    AttachedHeader, HeaderSource, header_schema,
};
use crate::bindings::_helpers::compiled_project::model_loop_hooks::{
    ExpandedHooks, HookModel, SqlHookClasses, expanded_hooks,
};
use crate::bindings::_helpers::compiled_project::model_loop_host::{
    FinishedModel, InterpolationRow, ModelLoopRow, RecordClasses, RecordInputs, ReferenceRow,
    finished_record,
};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::{
    analysis_override, hook_presence, reference_row,
};
use crate::bindings::_helpers::compiled_project::model_loop_macros::{
    ExpandedMacros, MacroClasses, MacroModel, expanded_macros,
};
use crate::bindings::_helpers::compiled_project::model_loop_named::{
    SCHEMA_DECLARATION, named_usages,
};
use crate::bindings::_helpers::compiled_project::model_loop_opt_out::{
    OptOut, OptOutModel, reject_unparseable_query, rejected_opt_out,
};
use crate::bindings::_helpers::compiled_project::model_loop_python_hooks::{
    HookClasses, HookSignatures,
};
use crate::bindings::_helpers::compiled_project::model_loop_schema::{
    ModelSchema, model_schema, schema_column_names,
};
use crate::bindings::_helpers::compiled_project::model_loop_visibility::{
    ModelVisibility, VisibilityClasses, VisibilityModel,
};
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;
use crate::bindings::_helpers::compiled_project::scenario_loop::ScenarioRow;
use crate::bindings::_helpers::compiled_project::source_loop::{
    SourceRow, SourceSettings, attached_sources,
};
use crate::bindings::_helpers::compiled_project::source_views::{
    AttachedSource, NativeSourceInput, retain_sources,
};
use crate::bindings::_helpers::compiled_project::sql_test_loop::{
    AttachedSqlTests, SqlTestSettings, TestFileRow, TestScope,
};
use crate::bindings::_helpers::model_config::header_metadata::ContractClasses;
use crate::bindings::_helpers::model_config::model_validator::NativeModelValidator;
use crate::bindings::_helpers::render::declaration_expansion::{
    DeclarationExpansion, ExpandedDeclarations, ExpansionClasses, ExpansionConsumer, SpanRow,
    expand_declarations,
};
use crate::bindings::_helpers::render::macro_call_rows::span_row;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;
use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods, PyTuple};
use pyo3::{FromPyObject, pyclass, pymethods};
use sqlbuild_analysis::compiled_project::main::analysis_gate::analysis_gate;
use sqlbuild_analysis::compiled_project::main::calls_macros::calls_macros;
use sqlbuild_analysis::compiled_project::main::legacy_schema_error::legacy_schema_error;
use sqlbuild_analysis::compiled_project::main::located_scan_error::located_scan_error;
use sqlbuild_analysis::compiled_project::main::merge_call_site_references::merge_call_site_references;
use sqlbuild_analysis::compiled_project::models::{
    AnalysisGate, LegacySchemaFile, ModelLoopSettings, ScanFaultOrigin, SplicedSpan,
};
use sqlbuild_attachments::cursor_intrinsics::main::validated_model_intrinsics::validated_model_intrinsics;
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicModel;
use sqlbuild_attachments::functions::models::KnownResources;
use sqlbuild_attachments::test_targets::models::TargetCatalog;
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::ReferenceExtraction;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;
use std::collections::{HashMap, HashSet};

const MATERIALIZED_KEY: &str = "materialized";
const CURSOR_KEY: &str = "cursor";
const INCREMENTAL_MATERIALIZATION: &str = "incremental";
const VALUES_ATTRIBUTE: &str = "values";
const RETENTION_ATTRIBUTE: &str = "time_travel_retention";
const UNMANAGED_ATTRIBUTE: &str = "unmanaged";
const TABLE_TYPE_ATTRIBUTE: &str = "table_type";
const DECLARED_ATTRIBUTE: &str = "declared";
const VALIDATE_METHOD: &str = "validate";
const FILE_PATH_ARGUMENT: &str = "file_path";
const CONSTANT_TEXT_CALLBACK: &str = "constant_text";
const HELP_ARGUMENT: &str = "help";
const ERROR_ARGUMENT: &str = "error";
const VALUES_ARGUMENT: &str = "values";
const CODE_ARGUMENT: &str = "code";
const ANALYSIS_CONFLICT: &str = "MODEL sql_analysis conflicts with legacy sql_validation";
const ANALYSIS_CONFLICT_CODE: &str = "P003";

/// The native validator, header contract classes, and the loop's Python classes.
type LoopChecks = (Py<PyAny>, Py<PyDict>, Py<PyDict>);
/// `(analysis switches, native syntax, (project config path, legacy schema files))`.
type LoopSettingsInput = (
    (bool, bool, bool, bool),
    (String, Vec<(String, Vec<String>)>),
);

/// The Python classes and error factory the loop builds usages, hooks and errors with.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct LoopClasses<'py> {
    pub(crate) usage_record: Bound<'py, PyAny>,
    pub(crate) compile_error: Bound<'py, PyAny>,
    pub(crate) sql_hook_entry: Bound<'py, PyAny>,
    /// `native_config_error`: the exception a native config error raises as.
    pub(crate) config_error: Bound<'py, PyAny>,
    /// Discovered audit factories by name.
    pub(crate) audit_factories: Bound<'py, PyDict>,
    /// `UsageKind.GENERATED`, for usages an enum-typed column generates.
    pub(crate) generated_usage: Bound<'py, PyAny>,
    /// `ContractPolicy.ENFORCED`.
    pub(crate) contract_enforced: Bound<'py, PyAny>,
    /// Public reusable model schemas by name.
    pub(crate) model_schemas: Bound<'py, PyDict>,
    /// Each indexed schema's and Python hook's declaration record, by `(kind, name)`.
    pub(crate) named_records: Bound<'py, PyDict>,
    /// Project enums by name, as a schema's column types resolve them.
    pub(crate) schema_enums: Bound<'py, PyDict>,
    /// `CompilerDiagnostic` and `report_compile_diagnostic`, for S006.
    pub(crate) compiler_diagnostic: Bound<'py, PyAny>,
    pub(crate) report_diagnostic: Bound<'py, PyAny>,
    /// `pathlib.Path`.
    pub(crate) path_class: Bound<'py, PyAny>,
    /// The dbt manifest's `ExternalSqlReferenceResolver`, or `None`.
    pub(crate) external_resolver: Bound<'py, PyAny>,
    /// `SqlReferenceKind`.
    pub(crate) reference_kind: Bound<'py, PyAny>,
    /// `functools.partial`, binding the model's file to its constant renderer.
    pub(crate) partial: Bound<'py, PyAny>,
    /// What a model's effective config is built from.
    pub(crate) config: ConfigClasses<'py>,
    /// What a model's visible declarations are resolved from.
    pub(crate) visibility: VisibilityClasses<'py>,
    /// What a model's Python hooks are checked against.
    pub(crate) hooks: HookClasses<'py>,
    /// What each model's SQL hooks are expanded with.
    pub(crate) sql_hooks: SqlHookClasses<'py>,
    /// What each model's macro calls are expanded with.
    pub(crate) macros: MacroClasses<'py>,
    /// `sql_analysis_opt_out_help(model_owned=True)`, the help of a model's syntax error.
    pub(crate) syntax_help: String,
    /// The same help for SQL a project's other resources own.
    pub(crate) source_syntax_help: String,
    /// `InvalidScopePathError`.
    pub(crate) scope_path_error: Bound<'py, PyAny>,
    /// What each finished model's input record is built with.
    pub(crate) record: RecordClasses<'py>,
    /// What model input views project their attributes with.
    pub(crate) input_view: Bound<'py, PyAny>,
}

/// The ordered model loop of one compile-input stage.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeModelLoop {
    pub(crate) validator: Py<PyAny>,
    pub(crate) syntax: LexicalSyntax,
    pub(crate) reserved_markers: Vec<String>,
    pub(crate) settings: ModelLoopSettings,
    pub(crate) project_config_path: String,
    legacy_schema_files: Vec<LegacySchemaFile>,
    contract_classes: Py<PyDict>,
    loop_classes: Py<PyDict>,
}

/// What one run reads beside each model: the host, Python classes and header contract classes.
pub(crate) struct LoopContext<'a, 'py> {
    pub(crate) host: &'a Bound<'py, PyAny>,
    pub(crate) classes: &'a LoopClasses<'py>,
    pub(crate) contracts: &'a ContractClasses<'py>,
}

/// The declarations a model sees and the identity its usages are recorded for.
pub(crate) struct VisibleDeclarations<'py> {
    pub(crate) declarations: Bound<'py, PyAny>,
    pub(crate) consumer: Bound<'py, PyAny>,
}

/// What the model loop knows about a model before finishing it.
struct LoopModel<'a, 'py> {
    row: &'a ModelLoopRow,
    config: Bound<'py, PyAny>,
    visible: &'a VisibleDeclarations<'py>,
    signatures: &'a HookSignatures,
    visibility: &'a ModelVisibility<'py>,
}

#[pymethods]
impl NativeModelLoop {
    #[new]
    fn new(
        checks: LoopChecks,
        syntax: LexicalSyntaxInput,
        reserved_markers: Vec<String>,
        settings: LoopSettingsInput,
    ) -> PyResult<Self> {
        let (validator, contract_classes, loop_classes) = checks;
        let (
            (sql_analysis, no_sql_validation, defer_sql_validation, require_sql_analysis),
            (project_config_path, legacy_schema_files),
        ) = settings;
        Ok(Self {
            validator,
            syntax: syntax.into(),
            reserved_markers,
            settings: ModelLoopSettings {
                sql_analysis,
                no_sql_validation,
                defer_sql_validation,
                require_sql_analysis,
            },
            project_config_path,
            legacy_schema_files: legacy_schema_files
                .into_iter()
                .map(|(relative_path, model_names)| LegacySchemaFile {
                    relative_path,
                    model_names,
                })
                .collect(),
            contract_classes,
            loop_classes,
        })
    }

    /// Build every model in order into `project`; return each model's input view.
    fn run<'py>(
        slf: &Bound<'py, Self>,
        project: Bound<'py, NativeCompiledProject>,
        host: Bound<'py, PyAny>,
        models: Vec<ModelLoopRow>,
    ) -> PyResult<Vec<Bound<'py, NativeModelInput>>> {
        let py: Python<'py> = slf.py();
        project
            .borrow_mut()
            .keep_attachment_loop(slf.clone().unbind(), host.clone().unbind());
        slf.get().run_models(py, project, host, models)
    }
}

impl NativeModelLoop {
    fn run_models<'py>(
        &self,
        py: Python<'py>,
        project: Bound<'py, NativeCompiledProject>,
        host: Bound<'py, PyAny>,
        models: Vec<ModelLoopRow>,
    ) -> PyResult<Vec<Bound<'py, NativeModelInput>>> {
        let contracts: ContractClasses<'py> = self.contract_classes.bind(py).extract()?;
        let classes: LoopClasses<'py> = self.loop_classes.bind(py).extract()?;
        let context: LoopContext<'_, 'py> = LoopContext {
            host: &host,
            classes: &classes,
            contracts: &contracts,
        };
        project
            .borrow_mut()
            .set_input_classes(classes.input_view.clone().unbind());
        let mut inputs: Vec<Bound<'py, NativeModelInput>> = Vec::with_capacity(models.len());
        let configs: ModelConfigs<'py> = ModelConfigs::default();
        let visibility: ModelVisibility<'py> = ModelVisibility::default();
        let signatures: HookSignatures = HookSignatures::default();
        for row in models {
            let ModelLoopRow((name, _, relative_path, file_path), header, _, _, _, _, _) = &row;
            let (_, header_values, enums, constants) = header;
            let visible: VisibleDeclarations<'py> = visibility.for_model(
                &context,
                &VisibilityModel {
                    name,
                    file_path,
                    local: (enums.bind(py), constants.bind(py)),
                },
            )?;
            let config: Bound<'py, PyAny> =
                configs.effective(&context, header_values.bind(py), (name, relative_path))?;
            let model: LoopModel<'_, 'py> = LoopModel {
                row: &row,
                config,
                visible: &visible,
                signatures: &signatures,
                visibility: &visibility,
            };
            let finished: FinishedModel<'py> = self.finish(py, &context, model)?;
            let record_inputs: RecordInputs<'_, 'py> = RecordInputs {
                classes: &classes.record,
                visible: &visible.declarations,
            };
            let (record, facts) = finished_record(&record_inputs, row, finished)?;
            let mut owner = project.borrow_mut();
            owner.retain(facts);
            let index: usize = owner.retain_input(record);
            drop(owner);
            inputs.push(Bound::new(
                py,
                NativeModelInput::new(project.clone().unbind(), index),
            )?);
        }
        Ok(inputs)
    }
}

impl NativeModelLoop {
    /// Attach every discovered source in order into `project`; return each source's view.
    pub(crate) fn run_sources<'py>(
        &self,
        project: &Bound<'py, NativeCompiledProject>,
        host: &Bound<'py, PyAny>,
        rows: Vec<SourceRow>,
        settings: SourceSettings,
    ) -> PyResult<Vec<NativeSourceInput>> {
        let py: Python<'py> = host.py();
        let contracts: ContractClasses<'py> = self.contract_classes.bind(py).extract()?;
        let classes: LoopClasses<'py> = self.loop_classes.bind(py).extract()?;
        let context: LoopContext<'_, 'py> = LoopContext {
            host,
            classes: &classes,
            contracts: &contracts,
        };
        let attached: Vec<AttachedSource> = attached_sources(self, &context, rows, settings)?;
        Ok(retain_sources(project, attached))
    }

    /// Attach every singular audit, then each owner's attached audits.
    pub(crate) fn run_audits<'py>(
        &self,
        host: &Bound<'py, PyAny>,
        files: &[AuditFileRow],
        owners: Vec<AttachmentOwner<'py>>,
        settings: &AuditSettings,
    ) -> PyResult<(Vec<AttachedAudit>, Vec<Bound<'py, PyAny>>)> {
        let py: Python<'py> = host.py();
        let contracts: ContractClasses<'py> = self.contract_classes.bind(py).extract()?;
        let classes: LoopClasses<'py> = self.loop_classes.bind(py).extract()?;
        let context: LoopContext<'_, 'py> = LoopContext {
            host,
            classes: &classes,
            contracts: &contracts,
        };
        attached_audits(self, &context, (files, owners), settings)
    }

    /// Attach every SQL test case, then every scenario, against the project's resources.
    pub(crate) fn run_sql_tests<'py>(
        &self,
        host: &Bound<'py, PyAny>,
        rows: (&[TestFileRow], &[ScenarioRow]),
        settings: &SqlTestSettings,
        table_function_arities: HashMap<String, usize>,
    ) -> PyResult<AttachedSqlTests> {
        let py: Python<'py> = host.py();
        let contracts: ContractClasses<'py> = self.contract_classes.bind(py).extract()?;
        let classes: LoopClasses<'py> = self.loop_classes.bind(py).extract()?;
        let context: LoopContext<'_, 'py> = LoopContext {
            host,
            classes: &classes,
            contracts: &contracts,
        };
        let validator: Bound<'py, NativeModelValidator> =
            self.validator.bind(py).downcast()?.clone();
        let known: KnownResources<'_> = validator.get().known_resources();
        let resolver: &Bound<'py, PyAny> = &classes.external_resolver;
        let extended =
            |names: &HashSet<String>, method: &str, keyword: &str| -> PyResult<HashSet<String>> {
                let mut names: HashSet<String> = names.clone();
                if !resolver.is_none() {
                    let arguments: Bound<'py, PyDict> = PyDict::new(py);
                    arguments.set_item(keyword, &names)?;
                    let added: HashSet<String> = resolver
                        .call_method(method, (), Some(&arguments))?
                        .extract()?;
                    names.extend(added);
                }
                Ok(names)
            };
        let models: HashSet<String> = extended(
            known.models,
            "extend_sql_test_model_names",
            "known_model_names",
        )?;
        let seeds: HashSet<String> = extended(
            known.seeds,
            "extend_sql_test_seed_names",
            "known_seed_names",
        )?;
        let sources: HashSet<String> = extended(
            known.sources,
            "extend_sql_test_source_names",
            "known_source_names",
        )?;
        let scope: TestScope<'_, 'py> = TestScope {
            model_loop: self,
            context: &context,
            settings,
            catalog: TargetCatalog {
                models,
                sources,
                seeds,
                table_functions: known.table_functions.clone(),
                macros: classes.macros.macro_names()?,
            },
            functions: known.functions.clone(),
            table_function_arities,
        };
        let tests: Vec<Py<PyAny>> = scope.attached(rows.0)?;
        let scenarios: Vec<Py<PyAny>> = scope.attached_scenarios(rows.1)?;
        Ok((tests, scenarios))
    }

    /// Attach every SQL, then Python, function in order, checking table function call arities.
    pub(crate) fn run_functions<'py>(
        &self,
        host: &Bound<'py, PyAny>,
        rows: (Vec<FunctionRow>, Vec<FunctionRow>),
        settings: FunctionSettings,
        models: &[(String, Vec<ReferenceRow>)],
    ) -> PyResult<Vec<AttachedFunction>> {
        let py: Python<'py> = host.py();
        let contracts: ContractClasses<'py> = self.contract_classes.bind(py).extract()?;
        let classes: LoopClasses<'py> = self.loop_classes.bind(py).extract()?;
        let context: LoopContext<'_, 'py> = LoopContext {
            host,
            classes: &classes,
            contracts: &contracts,
        };
        let attached: Vec<AttachedFunction> = attached_functions(self, &context, rows, settings)?;
        checked_table_function_arities(&context, models, &attached)?;
        Ok(attached)
    }

    /// Run the model's steps in the attachment's order; `None` hands it to the attachment.
    fn finish<'py>(
        &self,
        py: Python<'py>,
        context: &LoopContext<'_, 'py>,
        model: LoopModel<'_, 'py>,
    ) -> PyResult<FinishedModel<'py>> {
        let LoopModel {
            row,
            config,
            visible,
            signatures,
            visibility,
        } = model;
        let ModelLoopRow(
            (name, posix_path, relative_path, file_path),
            (locations, _, _, _),
            authored_query,
            contents,
            scan,
            interpolation,
            _,
        ) = row;
        let values: Bound<'py, PyDict> = config.getattr(VALUES_ATTRIBUTE)?.downcast_into()?;
        let schema: Option<ModelSchema<'py>> = model_schema(context, &values, name)?;
        let hooked: bool = hook_presence(&values)?;
        let python_hooks: Vec<Bound<'py, PyAny>> = if hooked {
            signatures.checked(context, &values, &visible.consumer, (name, relative_path))?
        } else {
            Vec::new()
        };
        let schema_usages: Vec<Bound<'py, PyAny>> = match &schema {
            Some(schema) => {
                let declaration = (&SCHEMA_DECLARATION, schema.name.as_str());
                named_usages(
                    context,
                    declaration,
                    &visible.consumer,
                    (name, relative_path),
                )?
            }
            None => Vec::new(),
        };
        let interpolated: String = applied_interpolation(context, interpolation)?;
        let (references, stop) = scan.clone().unwrap_or_default();
        let file_keyword: Bound<'py, PyDict> = PyDict::new(py);
        file_keyword.set_item(
            FILE_PATH_ARGUMENT,
            context.classes.path_class.call1((file_path,))?,
        )?;
        let render_constant: Bound<'py, PyAny> = context.classes.partial.call(
            (context.host.getattr(CONSTANT_TEXT_CALLBACK)?,),
            Some(&file_keyword),
        )?;
        let expansion_classes: ExpansionClasses<'py> = ExpansionClasses {
            usage_record: context.classes.usage_record.clone(),
            compile_error: context.classes.compile_error.clone(),
        };
        let declarations: ExpandedDeclarations<'py> = expand_declarations(&DeclarationExpansion {
            sql: &interpolated,
            references: &references,
            stop,
            context: &visible.declarations,
            consumer: ExpansionConsumer {
                identity: Some(visible.consumer.clone()),
                relationship_visibility: false,
                path: file_path,
            },
            render_constant: &render_constant,
            classes: &expansion_classes,
        })?;
        let macros: Option<ExpandedMacros> = if calls_macros(&declarations.spliced.sql) {
            let model: MacroModel<'_> = MacroModel {
                file_path,
                relative_path,
                contents,
                authored_query,
                authored: &interpolated == authored_query,
                declaration_spans: &declarations.spliced.spans,
            };
            Some(expanded_macros(
                context,
                visible,
                &declarations.spliced.sql,
                &model,
            )?)
        } else {
            None
        };
        let (macro_sql, argument_references, macro_spans): (
            String,
            Vec<ReferenceRow>,
            Vec<SpanRow>,
        ) = match &macros {
            Some(macros) => (
                macros.output.sql.clone(),
                macros.references.clone(),
                macros
                    .output
                    .spans
                    .iter()
                    .map(|span| span_row(*span))
                    .collect(),
            ),
            None => (declarations.spliced.sql.clone(), Vec::new(), Vec::new()),
        };
        let query_sql: String = self
            .canonical_query(name, &macro_sql, &values)?
            .map_err(|message| compile_error(context.classes, &message, None))?;
        let opt_out_model: OptOutModel<'_, 'py> = OptOutModel {
            name,
            file_path,
            config: &config,
            values: &values,
            query_sql: &query_sql,
            relative_path,
            contents,
        };
        let (analysed, rejected_opt_out) = self.analysis(context, &opt_out_model)?;
        let scanned = match extract_sql_references(&query_sql, &self.syntax) {
            ReferenceExtraction::Extracted(scanned) => scanned,
            ReferenceExtraction::Failed(failure) => {
                let authored: bool = &interpolated == authored_query && query_sql == macro_sql;
                let origin: ScanFaultOrigin<'_> = ScanFaultOrigin {
                    relative_path: posix_path,
                    contents,
                    query_sql: authored_query,
                    passes: authored.then(|| {
                        vec![
                            declarations.spliced.spans.clone(),
                            spliced_spans(&macro_spans),
                        ]
                    }),
                };
                let message: String =
                    located_scan_error(&failure, &query_sql, &origin, &self.syntax);
                return Err(compile_error(context.classes, &message, None));
            }
        };
        report_invalid_calls(
            context,
            &self.syntax,
            &scanned.invalid_calls,
            (Some(name), relative_path, file_path, contents),
        )?;
        let analysis: (bool, Option<Bound<'py, PyAny>>) = (
            analysed && scanned.invalid_calls.is_empty(),
            rejected_opt_out,
        );
        let references: Vec<ReferenceRow> = merge_call_site_references(
            scanned.references.iter().map(reference_row).collect(),
            argument_references,
        );
        let declared_columns: Option<Vec<String>> =
            schema.as_ref().map(schema_column_names).transpose()?;
        self.validate(
            context,
            (&config, &values),
            (name, &query_sql, relative_path),
            (&references, declared_columns),
        )?;
        let (values, hook_usages) = if hooked {
            let hook_model: HookModel<'_, 'py> = HookModel {
                name,
                posix_path,
                relative_path,
                file_path,
                contents,
                authored_query,
                visible,
                visibility,
            };
            let hooks: ExpandedHooks<'py> = expanded_hooks(self, context, &values, &hook_model)?;
            (hooks.values, hooks.usages)
        } else {
            (values, Vec::new())
        };
        let source: HeaderSource<'_, 'py> = HeaderSource {
            name,
            values: &values,
            locations: locations.bind(py),
            relative_path,
            visible: (&visible.declarations, &visible.consumer),
            schema: schema.as_ref(),
        };
        let header: AttachedHeader<'py> = header_schema(py, context, &source)?;
        if let Some(message) = legacy_schema_error((name, relative_path), &self.legacy_schema_files)
        {
            return Err(compile_error(context.classes, &message, None));
        }
        let mut named_usages: Vec<Bound<'py, PyAny>> = hook_usages;
        named_usages.extend(schema_usages);
        named_usages.extend(python_hooks);
        Ok(FinishedModel {
            config,
            values,
            query_sql,
            header,
            references,
            declarations,
            analysis,
            named_usages,
            macros: macros.map(|macros| macros.output),
        })
    }

    /// Whether the model's SQL is analysed and its rejected opt-out; syntax is checked unless deferred.
    fn analysis<'py>(
        &self,
        context: &LoopContext<'_, 'py>,
        model: &OptOutModel<'_, 'py>,
    ) -> PyResult<(bool, Option<Bound<'py, PyAny>>)> {
        let (analysed, rejected) =
            match analysis_gate(self.settings, analysis_override(model.values)?) {
                AnalysisGate::Conflict => {
                    return Err(compile_error(
                        context.classes,
                        ANALYSIS_CONFLICT,
                        Some(ANALYSIS_CONFLICT_CODE),
                    ));
                }
                AnalysisGate::Enabled => (true, None),
                AnalysisGate::Disabled => match rejected_opt_out(self, context, model)? {
                    OptOut::Accepted => (false, None),
                    OptOut::Rejected(location) => (true, Some(location)),
                },
            };
        if analysed && !self.settings.defer_sql_validation {
            reject_unparseable_query(context, model)?;
        }
        Ok((analysed, rejected))
    }

    /// The query with canonical cursor intrinsics, or the message the attachment raises.
    fn canonical_query(
        &self,
        name: &str,
        sql: &str,
        values: &Bound<'_, PyDict>,
    ) -> PyResult<Result<String, String>> {
        let incremental: bool = values.get_item(MATERIALIZED_KEY)?.is_some_and(|value| {
            value
                .downcast::<PyString>()
                .is_ok_and(|text| text.to_string_lossy() == INCREMENTAL_MATERIALIZATION)
        });
        let cursor: Option<String> = match values.get_item(CURSOR_KEY)? {
            Some(value) => match value.downcast::<PyString>() {
                Ok(text) => Some(text.to_string_lossy().into_owned()),
                Err(_) => None,
            },
            None => None,
        };
        let model: IntrinsicModel<'_> = IntrinsicModel {
            name,
            incremental,
            cursor: cursor.as_deref(),
        };
        Ok(validated_model_intrinsics(
            sql,
            &self.reserved_markers,
            &model,
        ))
    }

    /// Validate the model natively, raising the validator's first error as Python does.
    fn validate(
        &self,
        context: &LoopContext<'_, '_>,
        config: (&Bound<'_, PyAny>, &Bound<'_, PyDict>),
        model: (&str, &str, &str),
        references: (&[ReferenceRow], Option<Vec<String>>),
    ) -> PyResult<()> {
        let (references, declared_columns) = references;
        let py: Python<'_> = context.host.py();
        let (config, values) = config;
        let external: Vec<Option<PyErr>> = external_errors(context, references, model.2)?;
        let rows: Vec<(&str, &str, bool)> = references
            .iter()
            .zip(&external)
            .map(|((kind, name, _, _), error)| (kind.as_str(), name.as_str(), error.is_some()))
            .collect();
        let unmanaged: Bound<'_, PyAny> = config
            .getattr(RETENTION_ATTRIBUTE)?
            .getattr(UNMANAGED_ATTRIBUTE)?;
        let declared: Bound<'_, PyAny> = config
            .getattr(TABLE_TYPE_ATTRIBUTE)?
            .getattr(DECLARED_ATTRIBUTE)?;
        let outcome: Bound<'_, PyAny> = self.validator.bind(py).call_method1(
            VALIDATE_METHOD,
            (
                values.clone(),
                model,
                (rows, declared_columns, unmanaged, declared),
            ),
        )?;
        validation_outcome(context, &outcome, external, values)
    }
}

/// `_raise_validation_outcome`: nothing, the validator's error, or a rejected reference's error.
pub(crate) fn validation_outcome(
    context: &LoopContext<'_, '_>,
    outcome: &Bound<'_, PyAny>,
    external: Vec<Option<PyErr>>,
    values: &Bound<'_, PyDict>,
) -> PyResult<()> {
    if outcome.is_none() {
        return Ok(());
    }
    if let Ok(index) = outcome.extract::<usize>()
        && let Some(error) = external.into_iter().nth(index).flatten()
    {
        return Err(error);
    }
    Err(config_error(context.classes, outcome, Some(values)))
}

/// `applied_interpolation`: record the interpolation's template reads, then its SQL or error.
fn applied_interpolation(
    context: &LoopContext<'_, '_>,
    interpolation: &InterpolationRow,
) -> PyResult<String> {
    let (sql, reads, error, _) = interpolation;
    record_reads(context, reads)?;
    match error {
        Some(message) => Err(compile_error(context.classes, message, None)),
        None => Ok(sql.clone()),
    }
}

/// Record interpolation's environment and context reads for compile reuse.
pub(crate) fn record_reads(
    context: &LoopContext<'_, '_>,
    reads: &[(String, String)],
) -> PyResult<()> {
    if !reads.is_empty() {
        let py: Python<'_> = context.host.py();
        context
            .classes
            .config
            .record_template_reads
            .call1((PyTuple::new(py, reads)?,))?;
    }
    Ok(())
}

/// `CompileInputError(message, code=...)`, raised as the attachment raises it.
pub(crate) fn compile_error(classes: &LoopClasses<'_>, message: &str, code: Option<&str>) -> PyErr {
    let raised = (|| {
        let keywords: Bound<'_, PyDict> = PyDict::new(classes.compile_error.py());
        if let Some(code) = code {
            keywords.set_item(CODE_ARGUMENT, code)?;
        }
        classes.compile_error.call((message,), Some(&keywords))
    })();
    match raised {
        Ok(instance) => PyErr::from_value(instance),
        Err(failure) => failure,
    }
}

/// `CompileInputError(message, help=help)`.
pub(crate) fn helped_compile_error(
    classes: &LoopClasses<'_>,
    message: &str,
    help: Option<&str>,
) -> PyErr {
    let raised = (|| {
        let keywords: Bound<'_, PyDict> = PyDict::new(classes.compile_error.py());
        keywords.set_item(HELP_ARGUMENT, help)?;
        classes.compile_error.call((message,), Some(&keywords))
    })();
    match raised {
        Ok(instance) => PyErr::from_value(instance),
        Err(failure) => failure,
    }
}

/// The Python exception a native config error raises as, given the values it names.
pub(crate) fn config_error(
    classes: &LoopClasses<'_>,
    error: &Bound<'_, PyAny>,
    values: Option<&Bound<'_, PyDict>>,
) -> PyErr {
    let raised = (|| {
        let keywords: Bound<'_, PyDict> = PyDict::new(error.py());
        keywords.set_item(ERROR_ARGUMENT, error)?;
        keywords.set_item(VALUES_ARGUMENT, values)?;
        classes.config_error.call((), Some(&keywords))
    })();
    match raised {
        Ok(instance) => PyErr::from_value(instance),
        Err(failure) => failure,
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeModelLoop>()
}

/// Span rows as the spliced spans the scan-fault locator maps through.
fn spliced_spans(rows: &[SpanRow]) -> Vec<SplicedSpan> {
    rows.iter()
        .map(
            |&(source_start, source_end, output_start, output_end)| SplicedSpan {
                source_start,
                source_end,
                output_start,
                output_end,
            },
        )
        .collect()
}
