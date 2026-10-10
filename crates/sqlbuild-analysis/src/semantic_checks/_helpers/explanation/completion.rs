//! Python's `recover_diagnostics`, `explain_diagnostics` and opt-out rejection, in that order.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::LazyLock;

use regex::Regex;

use crate::semantic_checks::_helpers::explanation::columns::closest_column;
use crate::semantic_checks::_helpers::explanation::explain::{
    Binary, ExplainContext, ModelEvidence, Shapes, binary_index, explain_model, is_explained_code,
    is_type_code,
};
use crate::semantic_checks::_helpers::explanation::messages::{
    compiled, missing_column, pattern, semantic_help, sentence_message,
};
use crate::semantic_checks::_helpers::explanation::opt_outs::opt_out_diagnostic;
use crate::semantic_checks::_helpers::recovery::bindings::{BindingOwner, binding_positions};
use crate::semantic_checks::_helpers::recovery::poison::Poison;
use crate::semantic_checks::_helpers::sql_text::parsed_sql::{
    ParsedModelFacts, parsed_model_facts,
};
use crate::semantic_checks::_helpers::sql_text::text::LineIndex;
use crate::semantic_checks::constants::{
    MODEL_RESOURCE_TYPE, SEMANTIC_CODE_PREFIX, SQL_TEST_COLUMN_CODE, SQL_TEST_COLUMN_PATTERN,
    UNKNOWN_COLUMN_CODE,
};
use crate::semantic_checks::models::{
    CompletedDiagnostic, CompletionModel, CompletionOutcome, CompletionRequest, FinalDiagnostic,
    LineageOutput, SemanticDiagnostic, SemanticFailure,
};

static SQL_TEST_COLUMN: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| compiled(SQL_TEST_COLUMN_PATTERN));

/// Complete recovery, explanation and opt-out rejection.
pub(crate) fn complete(request: &CompletionRequest) -> Result<CompletionOutcome, SemanticFailure> {
    completed(request)
}

/// The request with its shapes and models indexed, and the parsed facts of failing models.
struct Completion<'a> {
    request: &'a CompletionRequest,
    shapes: Shapes<'a>,
    models: HashMap<&'a str, usize>,
    parsed: HashMap<usize, ParsedModelFacts>,
}

impl<'a> Completion<'a> {
    fn new(request: &'a CompletionRequest) -> Result<Self, SemanticFailure> {
        let models: HashMap<&'a str, usize> = request
            .models
            .iter()
            .enumerate()
            .map(|(index, model)| (model.name.as_str(), index))
            .collect();
        let mut parsed: HashMap<usize, ParsedModelFacts> = HashMap::new();
        for diagnostic in &request.diagnostics {
            let name: &str = diagnostic.resource_name.as_deref().unwrap_or("");
            let Some(index) = models.get(name).copied() else {
                continue;
            };
            if is_explained_code(&diagnostic.code) && !parsed.contains_key(&index) {
                let model = &request.models[index];
                let facts = parsed_model_facts(&model.query_sql, request.dialect.as_deref())?;
                parsed.insert(index, facts);
            }
        }
        Ok(Self {
            request,
            shapes: request
                .shapes
                .iter()
                .map(|(name, columns)| (name.as_str(), columns.as_slice()))
                .collect(),
            models,
            parsed,
        })
    }

    fn source(&self, diagnostic: &CompletedDiagnostic) -> &'a SemanticDiagnostic {
        &self.request.diagnostics[diagnostic.source]
    }

    fn model(&self, diagnostic: &CompletedDiagnostic) -> Option<(usize, &'a CompletionModel)> {
        let name: &str = self
            .source(diagnostic)
            .resource_name
            .as_deref()
            .unwrap_or("");
        self.models
            .get(name)
            .map(|index| (*index, &self.request.models[*index]))
    }

    fn facts(&self, index: usize) -> Result<&ParsedModelFacts, SemanticFailure> {
        self.parsed
            .get(&index)
            .ok_or_else(|| SemanticFailure::internal("a failing model without parsed facts"))
    }
}

fn completed(request: &CompletionRequest) -> Result<CompletionOutcome, SemanticFailure> {
    let completion = Completion::new(request)?;
    let initial: Vec<CompletedDiagnostic> = request
        .diagnostics
        .iter()
        .enumerate()
        .map(|(source, diagnostic)| CompletedDiagnostic {
            source,
            message: diagnostic.message.clone(),
            help: diagnostic.help.clone(),
            notes: diagnostic.notes.clone(),
            location: diagnostic.location,
            line: diagnostic.line,
            column: diagnostic.column,
            changed: false,
        })
        .collect();
    let mut codes: Vec<HashSet<&str>> = request
        .models
        .iter()
        .map(|model| model.binding_codes.iter().map(String::as_str).collect())
        .collect();
    let mut recovered_models: Option<Vec<Vec<usize>>> = None;
    let recovered: Vec<CompletedDiagnostic> = match recover(&completion, initial.clone())? {
        Some(recovered) => {
            let positions = positions(&completion, &recovered, &codes);
            codes = model_binding_codes(&completion, &recovered, &positions);
            recovered_models = Some(positions);
            recovered
        }
        None => initial,
    };
    let (diagnostics, model_bindings) = if recovered.is_empty() {
        (recovered, recovered_models)
    } else {
        let explained = explain(&completion, recovered)?;
        let bindings = positions(&completion, &explained, &codes);
        (explained, Some(bindings))
    };
    let order = reject_opt_outs(&completion, &diagnostics)?;
    Ok(CompletionOutcome {
        diagnostics,
        model_bindings,
        order,
    })
}

fn positions(
    completion: &Completion<'_>,
    diagnostics: &[CompletedDiagnostic],
    codes: &[HashSet<&str>],
) -> Vec<Vec<usize>> {
    let mut owners: Vec<BindingOwner<'_>> = Vec::with_capacity(diagnostics.len());
    for diagnostic in diagnostics {
        let source = completion.source(diagnostic);
        owners.push(BindingOwner {
            code: &source.code,
            is_model: source.resource_type.as_deref() == Some(MODEL_RESOURCE_TYPE),
            resource_name: source.resource_name.as_deref(),
        });
    }
    let mut models: Vec<(&str, HashSet<&str>)> = Vec::with_capacity(codes.len());
    for (model, model_codes) in completion.request.models.iter().zip(codes) {
        models.push((model.name.as_str(), model_codes.clone()));
    }
    binding_positions(&models, &owners)
}

/// The binding codes each model keeps after `update_binding_models`.
fn model_binding_codes<'a>(
    completion: &Completion<'a>,
    diagnostics: &[CompletedDiagnostic],
    positions: &[Vec<usize>],
) -> Vec<HashSet<&'a str>> {
    let mut codes: Vec<HashSet<&'a str>> = Vec::with_capacity(positions.len());
    for kept in positions {
        let mut model_codes: HashSet<&'a str> = HashSet::new();
        for position in kept {
            model_codes.insert(completion.source(&diagnostics[*position]).code.as_str());
        }
        codes.push(model_codes);
    }
    codes
}

/// True when `lineage` derives output `column` from `table.column`.
fn reads_input_column(lineage: &[LineageOutput], table: &str, column: &str) -> bool {
    for output in lineage {
        if output.output_column != column {
            continue;
        }
        for (resource, source) in &output.upstream {
            if resource == table && source == column {
                return true;
            }
        }
    }
    false
}

/// The poisoned output a B002 root error explains, as `(model, suggestion)`.
fn recovered_output(
    completion: &Completion<'_>,
    diagnostic: &CompletedDiagnostic,
) -> Result<Option<(String, String)>, SemanticFailure> {
    let Some((index, model)) = completion.model(diagnostic) else {
        return Ok(None);
    };
    let Some((column, table)) = missing_column(&diagnostic.message)? else {
        return Ok(None);
    };
    if !model.inferred_columns.contains(&column)
        || !completion.facts(index)?.unaliased_outputs.contains(&column)
    {
        return Ok(None);
    }
    let Some(table) = table else {
        return Ok(None);
    };
    if !reads_input_column(&model.lineage, &table, &column) {
        return Ok(None);
    }
    let columns: &[(String, String)] = completion
        .shapes
        .get(table.as_str())
        .copied()
        .unwrap_or_default();
    Ok(closest_column(&column, columns)?
        .map(|suggestion| (model.name.clone(), suggestion.to_owned())))
}

/// Python's `recover_diagnostics`, or `None` when it returns the project unchanged.
fn recover(
    completion: &Completion<'_>,
    diagnostics: Vec<CompletedDiagnostic>,
) -> Result<Option<Vec<CompletedDiagnostic>>, SemanticFailure> {
    let mut poisoned = Poison::default();
    let mut origins: HashMap<usize, (String, String)> = HashMap::new();
    let mut has_roots = false;
    for diagnostic in &diagnostics {
        if completion.source(diagnostic).code != UNKNOWN_COLUMN_CODE {
            continue;
        }
        has_roots = true;
        if let Some((model, suggestion)) = recovered_output(completion, diagnostic)? {
            let id = completion.source(diagnostic).id;
            poisoned.insert(&model, &suggestion, id);
            origins.insert(id, (model, suggestion));
        }
    }
    if !has_roots {
        return Ok(None);
    }
    poisoned.spread(
        completion
            .request
            .models
            .iter()
            .map(|model| (model.name.as_str(), model.lineage.as_slice())),
    );
    let mut skipped: Vec<((usize, String, String), usize)> = Vec::new();
    let mut kept: Vec<CompletedDiagnostic> = Vec::new();
    for diagnostic in diagnostics {
        let source = completion.source(&diagnostic);
        let target: Option<(String, String)> = recovery_target(&source.code, &diagnostic.message)?;
        let root = target
            .as_ref()
            .and_then(|(table, column)| poisoned.get(table, column));
        match root {
            Some(root) if root != source.id => {
                let (model, column) = origins.get(&root).cloned().unwrap_or_default();
                let key = (root, model, column);
                match skipped.iter().position(|(existing, _)| *existing == key) {
                    Some(position) => skipped[position].1 += 1,
                    None => skipped.push((key, 1)),
                }
            }
            _ => kept.push(diagnostic),
        }
    }
    let mut notes: HashMap<usize, Vec<String>> = HashMap::new();
    for ((root, model, column), count) in skipped {
        notes.entry(root).or_default().push(format!(
            "{count} downstream uses of {model}.{column} were not checked because of this error"
        ));
    }
    let mut annotated: Vec<CompletedDiagnostic> = Vec::with_capacity(kept.len());
    for mut diagnostic in kept {
        if let Some(extra) = notes.get(&completion.source(&diagnostic).id) {
            diagnostic.notes.extend(extra.iter().cloned());
            diagnostic.changed = true;
        }
        annotated.push(diagnostic);
    }
    Ok(Some(annotated))
}

/// The `(table, column)` use a diagnostic reports, which a poisoned output may explain.
fn recovery_target(code: &str, message: &str) -> Result<Option<(String, String)>, SemanticFailure> {
    let mut target: Option<(String, String)> = None;
    if code == UNKNOWN_COLUMN_CODE
        && let Some((column, Some(table))) = missing_column(message)?
    {
        target = Some((table, column));
    }
    if code == SQL_TEST_COLUMN_CODE
        && let Some(captures) = pattern(&SQL_TEST_COLUMN)?.captures(message)
    {
        target = Some((captures[1].to_owned(), captures[2].to_owned()));
    }
    Ok(target)
}

/// Python's `explain_diagnostics` over a non-empty diagnostic list.
fn explain(
    completion: &Completion<'_>,
    diagnostics: Vec<CompletedDiagnostic>,
) -> Result<Vec<CompletedDiagnostic>, SemanticFailure> {
    let mut binaries: HashMap<usize, Vec<Binary>> = HashMap::new();
    let mut explained: Vec<CompletedDiagnostic> = Vec::with_capacity(diagnostics.len());
    for diagnostic in diagnostics {
        let code: &str = &completion.source(&diagnostic).code;
        match completion.model(&diagnostic) {
            Some((index, model)) if is_explained_code(code) => {
                let authored_sql: &str = &model.authored_sql;
                if is_type_code(code) && !binaries.contains_key(&index) {
                    binaries.insert(index, binary_index(authored_sql)?);
                }
                let lines = LineIndex::new(authored_sql);
                let evidence = ModelEvidence {
                    authored_sql,
                    aliases: &completion.facts(index)?.aliases,
                    lines: &lines,
                    binaries: binaries.get(&index).map_or(&[], Vec::as_slice),
                };
                explained.push(explain_model(
                    &diagnostic,
                    &ExplainContext {
                        code,
                        model: &evidence,
                        shapes: &completion.shapes,
                        dialect: completion.request.dialect.as_deref(),
                    },
                )?);
            }
            _ => explained.push(with_semantic_help(diagnostic, code)?),
        }
    }
    Ok(explained)
}

/// Python's sentence message and code-owned help for a diagnostic outside a model.
fn with_semantic_help(
    diagnostic: CompletedDiagnostic,
    code: &str,
) -> Result<CompletedDiagnostic, SemanticFailure> {
    let Some(help) = semantic_help(code) else {
        return Ok(diagnostic);
    };
    let message = sentence_message(&diagnostic.message)?;
    let help = match diagnostic.help {
        Some(existing) if !existing.is_empty() => existing,
        _ => help.to_owned(),
    };
    Ok(CompletedDiagnostic {
        message,
        help: Some(help),
        changed: true,
        ..diagnostic
    })
}

/// True when opt-out rejection hides `diagnostic` behind the P009 error of its model.
fn hidden_by_opt_out(source: &SemanticDiagnostic, rejected: &BTreeMap<&str, usize>) -> bool {
    let rejected_model = source
        .resource_name
        .as_deref()
        .is_some_and(|name| rejected.contains_key(name));
    let model_resource = source
        .resource_type
        .as_deref()
        .is_none_or(|kind| kind == MODEL_RESOURCE_TYPE);
    rejected_model && model_resource && source.code.starts_with(SEMANTIC_CODE_PREFIX)
}

/// Python's `reject_unneeded_sql_analysis_opt_outs`: the final diagnostic order.
fn reject_opt_outs(
    completion: &Completion<'_>,
    diagnostics: &[CompletedDiagnostic],
) -> Result<Vec<FinalDiagnostic>, SemanticFailure> {
    let mut rejected: BTreeMap<&str, usize> = BTreeMap::new();
    for (index, model) in completion.request.models.iter().enumerate() {
        if model.rejected_opt_out_file.is_some() {
            rejected.insert(model.name.as_str(), index);
        }
    }
    let mut order: Vec<FinalDiagnostic> = Vec::new();
    let mut hidden: HashMap<&str, Vec<&str>> = HashMap::new();
    for (position, diagnostic) in diagnostics.iter().enumerate() {
        let source = completion.source(diagnostic);
        match source.resource_name.as_deref() {
            Some(name) if hidden_by_opt_out(source, &rejected) => {
                hidden.entry(name).or_default().push(&source.code);
            }
            _ => order.push(FinalDiagnostic::Completed(position)),
        }
    }
    for (name, index) in rejected {
        let model = &completion.request.models[index];
        let codes: &[&str] = hidden.get(name).map_or(&[], Vec::as_slice);
        order.push(FinalDiagnostic::OptOut(opt_out_diagnostic(
            index,
            &model.name,
            model.rejected_opt_out_file.as_deref(),
            codes,
        )?));
    }
    Ok(order)
}
