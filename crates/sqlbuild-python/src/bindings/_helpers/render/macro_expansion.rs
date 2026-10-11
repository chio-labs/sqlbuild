//! One authored string's macro expansion: scanned, memoised, evaluated and spliced natively.

use std::cell::RefCell;

use pyo3::exceptions::{PyIndexError, PyValueError};
use pyo3::prelude::{
    Bound, IntoPyObject, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyRef,
    PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyString, PyStringMethods, PyTuple};
use pyo3::{FromPyObject, pyclass, pymethods};
use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::is_python_decimal::is_python_decimal;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_render::macro_calls::main::scan_macro_call_sites::scan_macro_call_sites as scan_sites;
use sqlbuild_render::macro_calls::main::splice_macro_calls::splice_macro_calls as splice_calls;
use sqlbuild_render::macro_calls::models::{
    MacroCallEvent, MacroCallScan, MacroCallSite, MacroScanFailure,
};

use crate::bindings::_helpers::render::declaration_expansion::usage_visibility;
use crate::bindings::_helpers::render::macro_call_rows::{
    EventRow, SpanRow, event_from_row, event_row, span_row,
};
use crate::bindings::_helpers::render::macro_evaluation::{CallText, Evaluation, evaluate_call};
use crate::bindings::_helpers::render::macro_expansion_facts::{ExpansionFacts, ResourceRef};

const RELATION_PREFIX: &str = "__sqlbuild_relation_";
const RELATION_SUFFIX: &str = "__";
const CONSTANT_KIND: &str = "constant";
const RELATIONSHIP_CONSUMER_KINDS: [&str; 2] = ["test", "scenario"];

/// `(sql, spans, argument references, dependencies, usages)` of one expansion.
type ExpansionRow<'py> = (
    String,
    Vec<SpanRow>,
    Vec<ResourceRef>,
    Vec<Py<PyAny>>,
    Vec<Py<PyAny>>,
);

/// The Python classes, enums and helpers an expansion builds facts, errors and contexts from.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct ExpansionClasses<'py> {
    pub(crate) compile_error: Bound<'py, PyAny>,
    pub(crate) macro_argument_error: Bound<'py, PyAny>,
    mismatch_error: Bound<'py, PyAny>,
    declaration_identity: Bound<'py, PyAny>,
    declaration_kind: Bound<'py, PyAny>,
    macro_kind: Bound<'py, PyAny>,
    usage_record: Bound<'py, PyAny>,
    runtime_usage: Bound<'py, PyAny>,
    resource_identity: Bound<'py, PyAny>,
    model_kind: Bound<'py, PyAny>,
    pub(crate) resource_ref: Bound<'py, PyAny>,
    ref_kind: Bound<'py, PyAny>,
    /// `SqlResourceRefKind` member by typed reference function, such as `__ref`.
    pub(crate) ref_kinds: Bound<'py, PyDict>,
    /// Typed reference function by `SqlResourceRefKind` value.
    ref_functions: Bound<'py, PyDict>,
    macro_call_site: Bound<'py, PyAny>,
    pub(crate) relation_renderer: Bound<'py, PyAny>,
    /// Builds the `MacroContext` a macro is called with from the visible declarations.
    pub(crate) invocation_context: Bound<'py, PyAny>,
    /// Reports reference calls a macro returned and the references it generated.
    report_generated: Bound<'py, PyAny>,
    generated_markers: Vec<String>,
    /// Counts a call run outside the memo because a test mocks its macro.
    report_mocked: Bound<'py, PyAny>,
    pub(crate) int_type: Bound<'py, PyAny>,
    pub(crate) float_type: Bound<'py, PyAny>,
}

/// One authored string's expansion inputs and the facts it records.
#[pyclass(module = "sqlbuild._native", unsendable)]
pub(crate) struct NativeMacroExpansion {
    pub(crate) file_path: Py<PyAny>,
    pub(crate) file_label: String,
    pub(crate) loaded_macros: Py<PyDict>,
    pub(crate) overrides: Py<PyDict>,
    pub(crate) macro_context: Py<PyAny>,
    /// The visible `DeclarationResolutionContext`, or `None`.
    pub(crate) declarations: Py<PyAny>,
    /// The consumer usages are recorded for, or `None`.
    pub(crate) consumer: Py<PyAny>,
    enforce_explicit: bool,
    classes: Py<PyDict>,
    pub(crate) python: PythonText,
    pub(crate) facts: RefCell<ExpansionFacts>,
}

/// The `(macros, overrides, context, declarations, consumer)` one expansion reads.
type StateInput = (Py<PyDict>, Py<PyDict>, Py<PyAny>, Py<PyAny>, Py<PyAny>);

#[pymethods]
impl NativeMacroExpansion {
    #[new]
    fn new(
        file_path: &Bound<'_, PyAny>,
        state: StateInput,
        enforce_explicit: bool,
        classes: Py<PyDict>,
    ) -> PyResult<Self> {
        let (loaded_macros, overrides, macro_context, declarations, consumer) = state;
        Ok(Self {
            file_path: file_path.clone().unbind(),
            file_label: file_path.str()?.to_string(),
            loaded_macros,
            overrides,
            macro_context,
            declarations,
            consumer,
            enforce_explicit,
            classes,
            python: active_python_text(),
            facts: RefCell::new(ExpansionFacts::default()),
        })
    }

    /// Expand `sql`, through the bridge's memo when one is active.
    fn expand<'py>(
        this: PyRef<'py, Self>,
        sql: &Bound<'py, PyString>,
        bridge: &Bound<'py, PyAny>,
    ) -> PyResult<ExpansionRow<'py>> {
        let py: Python<'py> = sql.py();
        let classes: ExpansionClasses<'py> = this.classes.bind(py).extract()?;
        let handle: Bound<'py, PyAny> = (&this).into_pyobject(py)?.as_any().clone();
        let run: Evaluation<'_, 'py> = Evaluation {
            expansion: &this,
            handle: &handle,
            classes: &classes,
        };
        let text: CallText<'_> = CallText::new(sql.to_str()?);
        let scan: MacroCallScan = scan_sites(this.python, text.text);
        let call_classes: Option<Vec<Bound<'py, PyAny>>> = if bridge.is_none() {
            None
        } else {
            this.call_classes(&classes, bridge, &scan)?
        };
        let outputs: Vec<String> = match call_classes {
            Some(call_classes) => {
                let mut outputs: Vec<String> = Vec::with_capacity(scan.sites.len());
                for (site, call_class) in scan.sites.iter().zip(call_classes) {
                    outputs.push(this.bridged_output(&run, bridge, (&text, site), &call_class)?);
                }
                outputs
            }
            None => this.unmemoised_outputs(&run, &text, &scan)?,
        };
        let bounds: Vec<(usize, usize)> = scan
            .sites
            .iter()
            .map(|site| (site.start, site.end))
            .collect();
        let (rendered, spans) = splice_calls(text.text, &bounds, &outputs)
            .ok_or_else(|| PyValueError::new_err("macro call sites do not fit the SQL"))?;
        let facts = this.facts.borrow();
        Ok((
            rendered,
            spans.into_iter().map(span_row).collect(),
            facts.argument_references.clone(),
            facts
                .dependencies
                .iter()
                .map(|item| item.clone_ref(py))
                .collect(),
            facts.usages.iter().map(|item| item.clone_ref(py)).collect(),
        ))
    }

    /// `render_relation`: an approved call-site reference's placeholder, else its reference call.
    fn render_relation(&self, reference: &Bound<'_, PyAny>) -> PyResult<String> {
        let py: Python<'_> = reference.py();
        let classes: ExpansionClasses<'_> = self.classes.bind(py).extract()?;
        if !reference.is_instance(&classes.resource_ref)? {
            return Err(raised(
                &classes.compile_error,
                "Only typed resource references render as relations",
            ));
        }
        let key: ResourceRef = resource_key(reference)?;
        let index: Option<usize> = self.facts.borrow_mut().relation_index(&key);
        match index {
            Some(index) => Ok(format!("{RELATION_PREFIX}{index}{RELATION_SUFFIX}")),
            None => reference_call_text(&classes, &key),
        }
    }

    /// `_record_macro_declaration_usage`: a macro read a constant or enum through its context.
    fn declaration_read(&self, kind: &str, name: &str, py: Python<'_>) -> PyResult<()> {
        let classes: ExpansionClasses<'_> = self.classes.bind(py).extract()?;
        self.record_declaration_read(&classes, kind, name)
    }

    /// Mark the executing call as dependent on its consumer, so it is never replayed.
    fn block_memo(&self) {
        self.facts.borrow_mut().block_memo();
    }
}

impl NativeMacroExpansion {
    /// Each site's call class, or `None` when the scan failed or a tree name is unresolvable.
    fn call_classes<'py>(
        &self,
        classes: &ExpansionClasses<'py>,
        bridge: &Bound<'py, PyAny>,
        scan: &MacroCallScan,
    ) -> PyResult<Option<Vec<Bound<'py, PyAny>>>> {
        if scan.failure.is_some() {
            return Ok(None);
        }
        let py: Python<'py> = bridge.py();
        let mut found: Vec<Bound<'py, PyAny>> = Vec::with_capacity(scan.sites.len());
        for site in &scan.sites {
            let arguments: Bound<'py, PyDict> = PyDict::new(py);
            arguments.set_item("site", site_object(classes, site)?)?;
            arguments.set_item("declarations", self.declarations.bind(py))?;
            arguments.set_item("loaded_macros", self.loaded_macros.bind(py))?;
            arguments.set_item("macro_context", self.macro_context.bind(py))?;
            let call_class: Bound<'py, PyAny> =
                bridge.call_method("call_class", (), Some(&arguments))?;
            if call_class.is_none() {
                return Ok(None);
            }
            found.push(call_class);
        }
        Ok(Some(found))
    }

    /// `_bridged_call_output`: a recorded call replayed, or the call evaluated and recorded.
    fn bridged_output<'py>(
        &self,
        run: &Evaluation<'_, 'py>,
        bridge: &Bound<'py, PyAny>,
        call: (&CallText<'_>, &MacroCallSite),
        call_class: &Bound<'py, PyAny>,
    ) -> PyResult<String> {
        let (text, site) = call;
        let classes: &ExpansionClasses<'py> = run.classes;
        let py: Python<'py> = bridge.py();
        if self.mocked(site, py)? {
            let _ = classes.report_mocked.call0()?;
            return self.evaluated_output(run, (text, site));
        }
        let call_text: &str = text.slice(site.start, site.end);
        let prior: Option<Bound<'py, PyTuple>> = if site.typed_reference_text {
            let relations: Vec<ResourceRef> = self.facts.borrow().relations.clone();
            Some(reference_tuple(classes, &relations)?)
        } else {
            None
        };
        let lookup: Bound<'py, PyDict> = PyDict::new(py);
        lookup.set_item("call_class", call_class)?;
        lookup.set_item("call_text", call_text)?;
        lookup.set_item("prior_relations", prior.as_ref())?;
        let (class_id, recorded): (Bound<'py, PyAny>, Option<RecordedCall>) =
            bridge.call_method("lookup", (), Some(&lookup))?.extract()?;
        if let Some((recorded_sql, relations, events)) = recorded {
            for event in events {
                self.replay(classes, event_from_row(event)?)?;
            }
            for relation in &relations {
                let key: ResourceRef = resource_key(relation)?;
                let _ = self.facts.borrow_mut().relation_slot(&key);
            }
            return self.render_placeholders(classes, &recorded_sql);
        }
        let known: usize = self.facts.borrow().relations.len();
        self.facts.borrow_mut().begin_event_log();
        let result: PyResult<String> = top_level_output(run, (text, site));
        let (events, replayable) = self.facts.borrow_mut().end_event_log();
        let output: String = result?;
        let added: Vec<ResourceRef> = self.facts.borrow().relations[known..].to_vec();
        if replayable && (prior.is_some() || added.is_empty()) {
            let record: Bound<'py, PyDict> = PyDict::new(py);
            record.set_item("class_id", class_id)?;
            record.set_item("call_text", call_text)?;
            record.set_item("sql", &output)?;
            record.set_item("relations", reference_tuple(classes, &added)?)?;
            let rows: Vec<EventRow> = events.iter().map(event_row).collect();
            record.set_item("events", PyTuple::new(py, rows)?)?;
            let _ = bridge.call_method("record", (), Some(&record))?;
        }
        self.render_placeholders(classes, &output)
    }

    /// `_unmemoised_sql_macros`: every call evaluated in order, then the scan's failure raised.
    fn unmemoised_outputs(
        &self,
        run: &Evaluation<'_, '_>,
        text: &CallText<'_>,
        scan: &MacroCallScan,
    ) -> PyResult<Vec<String>> {
        let mut outputs: Vec<String> = Vec::with_capacity(scan.sites.len());
        for site in &scan.sites {
            outputs.push(self.evaluated_output(run, (text, site))?);
        }
        if let Some(failure) = &scan.failure {
            return Err(self.failed_scan(run.classes, failure, run.handle.py()));
        }
        Ok(outputs)
    }

    fn evaluated_output(
        &self,
        run: &Evaluation<'_, '_>,
        call: (&CallText<'_>, &MacroCallSite),
    ) -> PyResult<String> {
        let output: String = top_level_output(run, call)?;
        self.render_placeholders(run.classes, &output)
    }

    /// Whether a test overrides any macro in the call's tree.
    fn mocked(&self, site: &MacroCallSite, py: Python<'_>) -> PyResult<bool> {
        let overrides: &Bound<'_, PyDict> = self.overrides.bind(py);
        for name in site.tree_names.iter().flatten() {
            if overrides.contains(name)? {
                return Ok(true);
            }
        }
        Ok(false)
    }

    /// `raise_failed_macro_call`: the failing call's macro lookup error, else the scan's error.
    pub(crate) fn failed_scan(
        &self,
        classes: &ExpansionClasses<'_>,
        failure: &MacroScanFailure,
        py: Python<'_>,
    ) -> PyErr {
        if let Some(name) = &failure.call_name
            && let Err(error) = self.resolved_macro(classes, name, py)
        {
            return error;
        }
        raised(&classes.compile_error, failure.error.message())
    }

    /// `_resolved_macro`: the visible macro `name`, or Python's inaccessible or unknown error.
    pub(crate) fn resolved_macro<'py>(
        &self,
        classes: &ExpansionClasses<'py>,
        name: &str,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let declarations: &Bound<'py, PyAny> = self.declarations.bind(py);
        let macros: Bound<'py, PyAny> = if declarations.is_none() {
            self.loaded_macros.bind(py).clone().into_any()
        } else {
            declarations.getattr("macros")?
        };
        if !declarations.is_none() {
            let inaccessible: Bound<'py, PyAny> = declarations.getattr("inaccessible_macros")?;
            if inaccessible.contains(name)? {
                let record: Bound<'py, PyAny> = inaccessible.get_item(name)?;
                let owning: Bound<'py, PyAny> = record.getattr("owning_path")?;
                let owner: String = if owning.is_truthy()? {
                    owning.str()?.to_string()
                } else {
                    "global".to_owned()
                };
                let message: String = format!(
                    "Macro '@{name}' in '{}' is inaccessible. Defined at '{}:{}:{}' with scope \
                     owner '{owner}'; consumer/definition path is '{}'. Visible macros: {}",
                    self.file_label,
                    record.getattr("path")?.str()?,
                    record.getattr("line")?.str()?,
                    record.getattr("column")?.str()?,
                    self.file_label,
                    sorted_names(&macros)?,
                );
                return Err(raised(&classes.compile_error, &message));
            }
        }
        if macros.contains(name)? {
            return macros.get_item(name);
        }
        let message: String = format!(
            "Unknown macro '@{name}' in '{}'. Available macros: {}",
            self.file_label,
            sorted_names(&macros)?
        );
        Err(raised(&classes.compile_error, &message))
    }

    /// `_record_macro_use`: the macro's dependency and its runtime usage by the consumer.
    pub(crate) fn record_macro_use<'py>(
        &self,
        classes: &ExpansionClasses<'py>,
        name: &str,
        identity: &Bound<'py, PyAny>,
    ) -> PyResult<()> {
        let py: Python<'py> = identity.py();
        {
            let mut facts = self.facts.borrow_mut();
            facts.note_event(MacroCallEvent::MacroUse {
                name: name.to_owned(),
            });
            facts.dependencies.push(identity.clone().unbind());
        }
        let consumer: &Bound<'py, PyAny> = self.consumer.bind(py);
        if consumer.is_none() {
            return Ok(());
        }
        let declarations: &Bound<'py, PyAny> = self.declarations.bind(py);
        let visibility: Bound<'py, PyAny> = if declarations.is_none() {
            PyTuple::empty(py).into_any()
        } else {
            declarations
                .getattr("macro_visibility")?
                .call_method1("get", (name, PyTuple::empty(py)))?
        };
        let usages: Vec<Bound<'py, PyAny>> = if visibility.is_truthy()? {
            let mut usages: Vec<Bound<'py, PyAny>> = Vec::new();
            for visible in usage_visibility(&visibility, relationship_consumer(classes, consumer)?)?
            {
                usages.push(usage(
                    classes,
                    (consumer, identity),
                    Some(&visible.getattr("through")?),
                )?);
            }
            usages
        } else {
            vec![usage(classes, (consumer, identity), None)?]
        };
        self.facts
            .borrow_mut()
            .usages
            .extend(usages.into_iter().map(Bound::unbind));
        Ok(())
    }

    /// `_record_macro_declaration_usage` for a constant or enum the macro read.
    fn record_declaration_read(
        &self,
        classes: &ExpansionClasses<'_>,
        kind: &str,
        name: &str,
    ) -> PyResult<()> {
        let py: Python<'_> = classes.compile_error.py();
        self.facts
            .borrow_mut()
            .note_event(MacroCallEvent::DeclarationRead {
                kind: kind.to_owned(),
                name: name.to_owned(),
            });
        let declarations: &Bound<'_, PyAny> = self.declarations.bind(py);
        let own_consumer: &Bound<'_, PyAny> = self.consumer.bind(py);
        let consumer: Bound<'_, PyAny> = if own_consumer.is_truthy()? {
            own_consumer.clone()
        } else {
            declarations.getattr("consumer")?
        };
        if consumer.is_none() {
            return Ok(());
        }
        let constant: bool = kind == CONSTANT_KIND;
        let visibility: Bound<'_, PyAny> = declarations
            .getattr(if constant {
                "constant_visibility"
            } else {
                "enum_visibility"
            })?
            .call_method1("get", (name, PyTuple::empty(py)))?;
        let mut usages: Vec<Bound<'_, PyAny>> = Vec::new();
        if visibility.is_truthy()? {
            for visible in
                usage_visibility(&visibility, relationship_consumer(classes, &consumer)?)?
            {
                usages.push(usage(
                    classes,
                    (&consumer, &visible.getattr("declaration")?),
                    Some(&visible.getattr("through")?),
                )?);
            }
        } else {
            let declaration: Bound<'_, PyAny> = declarations
                .getattr(if constant { "constants" } else { "enums" })?
                .get_item(name)?;
            let model_name: Bound<'_, PyAny> = declaration.getattr("model_name")?;
            let owner: Option<Bound<'_, PyAny>> = if model_name.is_none() {
                None
            } else {
                let fields: Bound<'_, PyDict> = PyDict::new(py);
                fields.set_item("kind", &classes.model_kind)?;
                fields.set_item("name", model_name)?;
                Some(classes.resource_identity.call((), Some(&fields))?)
            };
            let fields: Bound<'_, PyDict> = PyDict::new(py);
            fields.set_item("kind", classes.declaration_kind.call1((kind,))?)?;
            fields.set_item("name", name)?;
            fields.set_item("owner", owner)?;
            let identity: Bound<'_, PyAny> =
                classes.declaration_identity.call((), Some(&fields))?;
            usages.push(usage(classes, (&consumer, &identity), None)?);
        }
        self.facts
            .borrow_mut()
            .usages
            .extend(usages.into_iter().map(Bound::unbind));
        Ok(())
    }

    /// `_report_generated_references` for a macro's returned SQL.
    pub(crate) fn report_generated(
        &self,
        classes: &ExpansionClasses<'_>,
        name: &str,
        loaded_macro: &Bound<'_, PyAny>,
        result: &str,
    ) -> PyResult<()> {
        if classes
            .generated_markers
            .iter()
            .any(|marker| result.contains(marker.as_str()))
        {
            self.facts
                .borrow_mut()
                .note_event(MacroCallEvent::GeneratedSql {
                    macro_name: name.to_owned(),
                    sql: result.to_owned(),
                });
        }
        let py: Python<'_> = loaded_macro.py();
        let arguments: Bound<'_, PyDict> = PyDict::new(py);
        arguments.set_item("loaded_macro", loaded_macro)?;
        arguments.set_item("macro_result", result)?;
        arguments.set_item("file_path", self.file_path.bind(py))?;
        arguments.set_item("consumer", self.consumer.bind(py))?;
        arguments.set_item("enforce_explicit", self.enforce_explicit)?;
        let _ = classes.report_generated.call((), Some(&arguments))?;
        Ok(())
    }

    /// `_replay_macro_call_event`: one recorded fact, recorded again for this consumer.
    fn replay(&self, classes: &ExpansionClasses<'_>, event: MacroCallEvent) -> PyResult<()> {
        let py: Python<'_> = classes.compile_error.py();
        match event {
            MacroCallEvent::MacroUse { name } => {
                let identity: Bound<'_, PyAny> = self.macro_identity(classes, &name, py)?;
                self.record_macro_use(classes, &name, &identity)
            }
            MacroCallEvent::DeclarationRead { kind, name } => {
                if self.declarations.bind(py).is_none() {
                    return Err(raised(
                        &classes.mismatch_error,
                        "Replayed a declaration read without declarations",
                    ));
                }
                self.record_declaration_read(classes, &kind, &name)
            }
            MacroCallEvent::GeneratedSql { macro_name, sql } => {
                let declarations: &Bound<'_, PyAny> = self.declarations.bind(py);
                let loaded_macro: Bound<'_, PyAny> = if declarations.is_none() {
                    self.loaded_macros
                        .bind(py)
                        .get_item(&macro_name)?
                        .ok_or_else(|| {
                            PyErr::new::<pyo3::exceptions::PyKeyError, _>(macro_name.clone())
                        })?
                } else {
                    declarations.getattr("macros")?.get_item(&macro_name)?
                };
                self.report_generated(classes, &macro_name, &loaded_macro, &sql)
            }
            MacroCallEvent::ArgumentReference { kind, name } => {
                self.facts
                    .borrow_mut()
                    .record_call_site_refs(&[(kind, name)]);
                Ok(())
            }
        }
    }

    /// The macro's declaration identity: its indexed record's, else an unowned macro identity.
    pub(crate) fn macro_identity<'py>(
        &self,
        classes: &ExpansionClasses<'py>,
        name: &str,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let declarations: &Bound<'py, PyAny> = self.declarations.bind(py);
        if !declarations.is_none() {
            return declarations
                .getattr("macro_records")?
                .get_item(name)?
                .getattr("identity");
        }
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        fields.set_item("kind", &classes.macro_kind)?;
        fields.set_item("name", name)?;
        classes.declaration_identity.call((), Some(&fields))
    }

    /// `render_relation_placeholders`: each placeholder as the reference call it stands for.
    fn render_placeholders(&self, classes: &ExpansionClasses<'_>, sql: &str) -> PyResult<String> {
        let relations: Vec<ResourceRef> = self.facts.borrow().relations.clone();
        if relations.is_empty() || !sql.contains(RELATION_PREFIX) {
            return Ok(sql.to_owned());
        }
        let mut rendered: String = String::with_capacity(sql.len());
        let mut cursor: usize = 0;
        let mut search: usize = 0;
        while let Some(found) = sql[search..].find(RELATION_PREFIX) {
            let start: usize = search + found;
            let digits_start: usize = start + RELATION_PREFIX.len();
            let digits_end: usize = sql[digits_start..]
                .char_indices()
                .find(|(_, character)| !is_python_decimal(self.python, *character))
                .map_or(sql.len(), |(offset, _)| digits_start + offset);
            if digits_end == digits_start || !sql[digits_end..].starts_with(RELATION_SUFFIX) {
                search = start + 1;
                continue;
            }
            let index: usize = classes
                .int_type
                .call1((&sql[digits_start..digits_end],))?
                .extract()?;
            let relation: &ResourceRef = relations
                .get(index)
                .ok_or_else(|| PyIndexError::new_err("tuple index out of range"))?;
            rendered.push_str(&sql[cursor..start]);
            rendered.push_str(&reference_call_text(classes, relation)?);
            cursor = digits_end + RELATION_SUFFIX.len();
            search = cursor;
        }
        rendered.push_str(&sql[cursor..]);
        Ok(rendered)
    }
}

/// One top-level call's SQL.
fn top_level_output(
    run: &Evaluation<'_, '_>,
    call: (&CallText<'_>, &MacroCallSite),
) -> PyResult<String> {
    evaluate_call(run, call, true)?.extract()
}

/// `(sql, relations, events)` of a recorded call as the bridge returns it.
type RecordedCall<'py> = (String, Vec<Bound<'py, PyAny>>, Vec<EventRow>);

/// The Python `MacroCallSite` the bridge classifies.
fn site_object<'py>(
    classes: &ExpansionClasses<'py>,
    site: &MacroCallSite,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = classes.macro_call_site.py();
    let fields: Bound<'py, PyDict> = PyDict::new(py);
    fields.set_item("start", site.start)?;
    fields.set_item("args_start", site.args_start)?;
    fields.set_item("end", site.end)?;
    fields.set_item("name", &site.name)?;
    fields.set_item(
        "tree_names",
        site.tree_names
            .as_ref()
            .map(|names| PyTuple::new(py, names))
            .transpose()?,
    )?;
    fields.set_item("typed_reference_text", site.typed_reference_text)?;
    classes.macro_call_site.call((), Some(&fields))
}

/// `SqlResourceRef` objects for typed references, in order.
pub(crate) fn reference_tuple<'py>(
    classes: &ExpansionClasses<'py>,
    references: &[ResourceRef],
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = classes.resource_ref.py();
    let mut objects: Vec<Bound<'py, PyAny>> = Vec::with_capacity(references.len());
    for (kind, name) in references {
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        fields.set_item("kind", classes.ref_kind.call1((kind,))?)?;
        fields.set_item("name", name)?;
        objects.push(classes.resource_ref.call((), Some(&fields))?);
    }
    PyTuple::new(py, objects)
}

/// A `SqlResourceRef`'s kind value and name.
pub(crate) fn resource_key(reference: &Bound<'_, PyAny>) -> PyResult<ResourceRef> {
    Ok((
        reference.getattr("kind")?.getattr("value")?.extract()?,
        reference.getattr("name")?.extract()?,
    ))
}

/// `reference_call_text`: the reference call naming `reference`, such as `__ref("orders")`.
fn reference_call_text(
    classes: &ExpansionClasses<'_>,
    reference: &ResourceRef,
) -> PyResult<String> {
    let (kind, name) = reference;
    let function: String = classes
        .ref_functions
        .get_item(kind)?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>(kind.clone()))?
        .extract()?;
    Ok(format!("{function}(\"{name}\")"))
}

/// Whether the consumer is a test or scenario, which records relationship visibility.
fn relationship_consumer(
    classes: &ExpansionClasses<'_>,
    consumer: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    if !consumer.is_instance(&classes.resource_identity)? {
        return Ok(false);
    }
    let kind: String = consumer.getattr("kind")?.getattr("value")?.extract()?;
    Ok(RELATIONSHIP_CONSUMER_KINDS.contains(&kind.as_str()))
}

/// A runtime `UsageRecord` of `declaration` by `consumer`, through a relationship if any.
fn usage<'py>(
    classes: &ExpansionClasses<'py>,
    usage: (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    through: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let (consumer, declaration) = usage;
    let keywords: Bound<'py, PyDict> = PyDict::new(consumer.py());
    if let Some(through) = through {
        keywords.set_item("through", through)?;
    }
    classes.usage_record.call(
        (consumer, declaration, &classes.runtime_usage),
        Some(&keywords),
    )
}

/// `", ".join(sorted(names)) or "none"`.
fn sorted_names(names: &Bound<'_, PyAny>) -> PyResult<String> {
    let mut sorted: Vec<String> =
        PyList::new(names.py(), names.try_iter()?.collect::<PyResult<Vec<_>>>()?)?.extract()?;
    sorted.sort_unstable();
    Ok(if sorted.is_empty() {
        "none".to_owned()
    } else {
        sorted.join(", ")
    })
}

/// The exception `class(message)` builds.
pub(crate) fn raised(class: &Bound<'_, PyAny>, message: &str) -> PyErr {
    match class.call1((message,)) {
        Ok(instance) => PyErr::from_value(instance),
        Err(error) => error,
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeMacroExpansion>()?;
    Ok(())
}
