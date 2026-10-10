//! The compile-input model loop: each model's steps run in the attachment's order, natively.

use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyRefMut, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods};
use pyo3::{FromPyObject, IntoPyObject, pyclass, pymethods};
use sqlbuild_analysis::compiled_project::main::analysis_gate::analysis_gate;
use sqlbuild_analysis::compiled_project::main::calls_macros::calls_macros;
use sqlbuild_analysis::compiled_project::main::header_attachment_feature::header_attachment_feature;
use sqlbuild_analysis::compiled_project::main::legacy_schema_error::legacy_schema_error;
use sqlbuild_analysis::compiled_project::main::merge_call_site_references::merge_call_site_references;
use sqlbuild_analysis::compiled_project::models::{
    AnalysisGate, AttachmentFeature, LegacySchemaFile, ModelLoopSettings,
};
use sqlbuild_attachments::cursor_intrinsics::main::validated_model_intrinsics::validated_model_intrinsics;
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicModel;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::ReferenceExtraction;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::compiled_project::model_loop_header::{
    AttachedHeader, HeaderSource, header_schema,
};
use crate::bindings::_helpers::compiled_project::model_loop_hooks::expanded_hooks;
use crate::bindings::_helpers::compiled_project::model_loop_host::{
    FinishedModel, ModelLoopRow, ReferenceRow, attached_input, callback, plain_input,
};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::{
    analysis_override, config_keys, hook_presence, reference_row,
};
use crate::bindings::_helpers::compiled_project::model_loop_opt_out::{
    OptOut, OptOutModel, rejected_opt_out,
};
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;
use crate::bindings::_helpers::discovery::project_files::python_semantics;
use crate::bindings::_helpers::model_config::header_metadata::ContractClasses;
use crate::bindings::_helpers::render::declaration_expansion::{
    DeclarationExpansion, ExpandedDeclarations, ExpansionClasses, ExpansionConsumer,
    expand_declarations, span_rows,
};
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;

const MATERIALIZED_KEY: &str = "materialized";
const CURSOR_KEY: &str = "cursor";
const INCREMENTAL_MATERIALIZATION: &str = "incremental";
const DBT_REF_KIND: &str = "dbt_ref";
const VALUES_ATTRIBUTE: &str = "values";
const RETENTION_ATTRIBUTE: &str = "time_travel_retention";
const UNMANAGED_ATTRIBUTE: &str = "unmanaged";
const TABLE_TYPE_ATTRIBUTE: &str = "table_type";
const DECLARED_ATTRIBUTE: &str = "declared";
const VALIDATE_METHOD: &str = "validate";
const CONFIG_CALLBACK: &str = "config";
const CHECK_HOOKS_CALLBACK: &str = "check_hooks";
const INTERPOLATE_CALLBACK: &str = "interpolate";
const EXPAND_MACROS_CALLBACK: &str = "expand_macros";
const CONSTANT_TEXT_CALLBACK: &str = "constant_text";
const INDEX_ARGUMENT: &str = "index";
const SQL_ARGUMENT: &str = "sql";
const SPANS_ARGUMENT: &str = "spans";
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
    bool,
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
}

/// The ordered model loop of one compile-input stage.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeModelLoop {
    pub(crate) validator: Py<PyAny>,
    syntax: LexicalSyntax,
    pub(crate) reserved_markers: Vec<String>,
    pub(crate) python: PythonText,
    pub(crate) settings: ModelLoopSettings,
    /// Whether project assembly answers SQL syntax natively in this compile.
    pub(crate) native_syntax: bool,
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
    index: usize,
    row: &'a ModelLoopRow,
    config: Bound<'py, PyAny>,
    visible: &'a VisibleDeclarations<'py>,
}

#[pymethods]
impl NativeModelLoop {
    #[new]
    fn new(
        checks: LoopChecks,
        syntax: LexicalSyntaxInput,
        cursor: (Vec<String>, ((u8, u8), String)),
        settings: LoopSettingsInput,
    ) -> PyResult<Self> {
        let (validator, contract_classes, loop_classes) = checks;
        let (reserved_markers, (python_version, unicode_version)) = cursor;
        let (
            (sql_analysis, no_sql_validation, defer_sql_validation, require_sql_analysis),
            native_syntax,
            (project_config_path, legacy_schema_files),
        ) = settings;
        Ok(Self {
            validator,
            syntax: syntax.into(),
            reserved_markers,
            python: python_semantics(python_version, &unicode_version)?,
            settings: ModelLoopSettings {
                sql_analysis,
                no_sql_validation,
                defer_sql_validation,
                require_sql_analysis,
            },
            native_syntax,
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

    /// Build every model in order into `project`; return the Python views and the native count.
    fn run<'py>(
        &self,
        py: Python<'py>,
        mut project: PyRefMut<'py, NativeCompiledProject>,
        host: Bound<'py, PyAny>,
        models: Vec<ModelLoopRow>,
    ) -> PyResult<(Vec<Bound<'py, PyAny>>, usize)> {
        let contracts: ContractClasses<'py> = self.contract_classes.bind(py).extract()?;
        let classes: LoopClasses<'py> = self.loop_classes.bind(py).extract()?;
        let context: LoopContext<'_, 'py> = LoopContext {
            host: &host,
            classes: &classes,
            contracts: &contracts,
        };
        let mut inputs: Vec<Bound<'py, PyAny>> = Vec::with_capacity(models.len());
        let mut finished_natively: usize = 0;
        for (index, row) in models.into_iter().enumerate() {
            let index_argument = [(INDEX_ARGUMENT, index.into_pyobject(py)?.into_any())];
            let (config, declarations, consumer): (
                Bound<'py, PyAny>,
                Bound<'py, PyAny>,
                Bound<'py, PyAny>,
            ) = callback(&host, CONFIG_CALLBACK, &index_argument)?.extract()?;
            let visible: VisibleDeclarations<'py> = VisibleDeclarations {
                declarations,
                consumer,
            };
            let model: LoopModel<'_, 'py> = LoopModel {
                index,
                row: &row,
                config,
                visible: &visible,
            };
            let (input, facts) = match self.finish(py, &context, model)? {
                Some(finished) => {
                    finished_natively += 1;
                    plain_input(&host, index, row, finished)?
                }
                None => attached_input(&host, &index_argument)?,
            };
            project.retain(facts);
            inputs.push(input);
        }
        Ok((inputs, finished_natively))
    }
}

impl NativeModelLoop {
    /// Run the model's steps in the attachment's order; `None` hands it to the attachment.
    fn finish<'py>(
        &self,
        py: Python<'py>,
        context: &LoopContext<'_, 'py>,
        model: LoopModel<'_, 'py>,
    ) -> PyResult<Option<FinishedModel<'py>>> {
        let LoopModel {
            index,
            row,
            config,
            visible,
        } = model;
        let ModelLoopRow((name, _, relative_path, file_path), locations, _, contents, scan) = row;
        let values: Bound<'py, PyDict> = config.getattr(VALUES_ATTRIBUTE)?.downcast_into()?;
        if header_attachment_feature(&config_keys(&values)?) == Some(AttachmentFeature::ModelSchema)
        {
            return Ok(None);
        }
        let index_argument = [(INDEX_ARGUMENT, index.into_pyobject(py)?.into_any())];
        let hooked: bool = hook_presence(&values)?;
        if hooked {
            callback(context.host, CHECK_HOOKS_CALLBACK, &index_argument)?;
        }
        let interpolated: String =
            callback(context.host, INTERPOLATE_CALLBACK, &index_argument)?.extract()?;
        let (references, stop) = scan.clone().unwrap_or_default();
        let render_constant: Bound<'py, PyAny> = context.host.getattr(CONSTANT_TEXT_CALLBACK)?;
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
        let (macro_sql, argument_references): (String, Vec<ReferenceRow>) =
            if calls_macros(&declarations.spliced.sql) {
                callback(
                    context.host,
                    EXPAND_MACROS_CALLBACK,
                    &[
                        (INDEX_ARGUMENT, index.into_pyobject(py)?.into_any()),
                        (
                            SQL_ARGUMENT,
                            declarations
                                .spliced
                                .sql
                                .as_str()
                                .into_pyobject(py)?
                                .into_any(),
                        ),
                        (
                            SPANS_ARGUMENT,
                            span_rows(&declarations.spliced).into_pyobject(py)?,
                        ),
                    ],
                )?
                .extract()?
            } else {
                (declarations.spliced.sql.clone(), Vec::new())
            };
        let query_sql: String = self
            .canonical_query(name, &macro_sql, &values)?
            .map_err(|message| compile_error(context.classes, &message, None))?;
        let opt_out_model: OptOutModel<'_, 'py> = OptOutModel {
            config: &config,
            values: &values,
            query_sql: &query_sql,
            relative_path,
            contents,
        };
        let Some((analysed, rejected_opt_out)) = self.analysis(context, &opt_out_model)? else {
            return Ok(None);
        };
        let ReferenceExtraction::Extracted(scanned) =
            extract_sql_references(&query_sql, &self.syntax)
        else {
            return Ok(None);
        };
        if scanned
            .references
            .iter()
            .any(|reference| reference.kind == DBT_REF_KIND)
        {
            return Ok(None);
        }
        let analysis: (bool, Option<Bound<'py, PyAny>>) = (
            analysed && scanned.invalid_calls.is_empty(),
            rejected_opt_out,
        );
        let references: Vec<ReferenceRow> = merge_call_site_references(
            scanned.references.iter().map(reference_row).collect(),
            argument_references,
        );
        self.validate(
            context,
            (&config, &values),
            (name, &query_sql, relative_path),
            &references,
        )?;
        let (values, hook_statements): (Bound<'py, PyDict>, usize) = if hooked {
            let Some(expanded) = expanded_hooks(self, context, index, (name, relative_path))?
            else {
                return Ok(None);
            };
            expanded
        } else {
            (values, 0)
        };
        let source: HeaderSource<'_, 'py> = HeaderSource {
            name,
            values: &values,
            locations: locations.bind(py),
            relative_path,
            visible: (&visible.declarations, &visible.consumer),
        };
        let header: AttachedHeader<'py> = header_schema(py, context, &source)?;
        if let Some(message) = legacy_schema_error((name, relative_path), &self.legacy_schema_files)
        {
            return Err(compile_error(context.classes, &message, None));
        }
        Ok(Some(FinishedModel {
            config,
            values,
            query_sql,
            header,
            references,
            declarations,
            hook_statements,
            analysis,
        }))
    }

    /// Whether the model's SQL is analysed and its rejected opt-out; `None` hands it over.
    fn analysis<'py>(
        &self,
        context: &LoopContext<'_, 'py>,
        model: &OptOutModel<'_, 'py>,
    ) -> PyResult<Option<(bool, Option<Bound<'py, PyAny>>)>> {
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
                    OptOut::Deferred => return Ok(None),
                },
            };
        if analysed && !self.settings.defer_sql_validation {
            return Ok(None);
        }
        Ok(Some((analysed, rejected)))
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
            self.python,
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
        references: &[ReferenceRow],
    ) -> PyResult<()> {
        let py: Python<'_> = context.host.py();
        let (config, values) = config;
        let rows: Vec<(&str, &str, bool)> = references
            .iter()
            .map(|(kind, name, _, _)| (kind.as_str(), name.as_str(), false))
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
                (rows, py.None(), unmanaged, declared),
            ),
        )?;
        if outcome.is_none() {
            return Ok(());
        }
        Err(config_error(context.classes, &outcome, Some(values)))
    }
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
