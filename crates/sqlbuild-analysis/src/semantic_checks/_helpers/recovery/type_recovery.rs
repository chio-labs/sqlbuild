//! Python's `recover_output_types`: unknown types for outputs poisoned by located root errors.

use std::collections::{HashMap, HashSet, VecDeque};

use crate::semantic_checks::_helpers::recovery::bindings::{BindingOwner, binding_positions};
use crate::semantic_checks::_helpers::recovery::poison::Poison;
use crate::semantic_checks::_helpers::sql_text::parsed_sql::{normalized_sql, projection_spans};
use crate::semantic_checks::models::{
    RecoveryModel, SemanticFailure, TypeRecoveryOutcome, TypeRecoveryPlan, TypeRecoveryRequest,
    TypeRecoveryStep,
};
use crate::semantic_checks::types::RevisedBinding;

/// Find poisoned outputs and the failed models Python must revalidate with unknown types.
pub(crate) fn plan(request: &TypeRecoveryRequest) -> Result<TypeRecoveryStep, SemanticFailure> {
    planned(request)
}

fn planned(request: &TypeRecoveryRequest) -> Result<TypeRecoveryStep, SemanticFailure> {
    let failed: Vec<usize> = failed_models(request);
    if !has_blocking_error(request, &failed) {
        return Ok(TypeRecoveryStep::Unchanged);
    }
    let dialect = request.dialect.as_deref();
    let sqls: Vec<String> = failed
        .iter()
        .map(|index| normalized_sql(&request.models[*index].query_sql, dialect))
        .collect::<Result<_, _>>()?;
    let errors: HashMap<usize, bool> = error_ids(request);
    let mut poisoned = Poison::default();
    let mut roots_by_model: HashMap<usize, HashMap<usize, usize>> = HashMap::new();
    let mut outputs_by_diagnostic: HashMap<usize, HashSet<String>> = HashMap::new();
    for (index, sql) in failed.iter().zip(&sqls) {
        let model: &RecoveryModel = &request.models[*index];
        let roots = root_bindings(model);
        let spans = projection_spans(sql, dialect)?;
        let columns: &[String] = model.inferred_columns.as_deref().unwrap_or_default();
        if spans.len() == columns.len() {
            let starts: Vec<usize> = spans.iter().map(|(start, _)| *start).collect();
            for raw in &model.raw_bindings {
                let Some(offset) = raw.start else {
                    continue;
                };
                let root = roots.get(&raw.id).copied();
                let column = column_at(columns, &spans, &starts, offset);
                if let (Some(root), Some(column)) = (root, column)
                    && errors.get(&root).copied().unwrap_or(false)
                {
                    poisoned.insert(&model.name, column, root);
                    outputs_by_diagnostic
                        .entry(root)
                        .or_default()
                        .insert(column.clone());
                }
            }
        }
        roots_by_model.insert(*index, roots);
    }
    if poisoned.is_empty() {
        return Ok(TypeRecoveryStep::Unchanged);
    }
    poisoned.spread(
        request
            .models
            .iter()
            .map(|model| (model.name.as_str(), model.lineage.as_slice())),
    );
    let mut causes_by_model: Vec<(usize, HashSet<usize>)> = Vec::new();
    for index in &failed {
        let causes = reference_causes(&request.models[*index], &poisoned);
        if !causes.is_empty() {
            causes_by_model.push((*index, causes));
        }
    }
    Ok(TypeRecoveryStep::Planned(TypeRecoveryPlan {
        poisoned: poisoned
            .entries()
            .map(|(key, root)| (key.clone(), root))
            .collect(),
        roots_by_model,
        outputs_by_diagnostic,
        causes_by_model,
    }))
}

/// Retain diagnostics the revalidation still reports and count unchecked downstream uses.
pub(crate) fn finish(
    request: &TypeRecoveryRequest,
    plan: &TypeRecoveryPlan,
    revised: &[Vec<RevisedBinding>],
) -> TypeRecoveryOutcome {
    let mut poisoned = Poison::default();
    for ((model, column), root) in &plan.poisoned {
        poisoned.insert(model, column, *root);
    }
    let mut skipped: HashSet<usize> = HashSet::new();
    let mut redirected: HashMap<usize, HashSet<usize>> = HashMap::new();
    let empty: HashMap<usize, usize> = HashMap::new();
    for ((index, causes), rows) in plan.causes_by_model.iter().zip(revised) {
        let model: &RecoveryModel = &request.models[*index];
        let remaining: HashSet<&RevisedBinding> = rows.iter().collect();
        let roots = plan.roots_by_model.get(index).unwrap_or(&empty);
        for raw in &model.raw_bindings {
            let Some(diagnostic) = roots.get(&raw.id).copied() else {
                continue;
            };
            let key: RevisedBinding = (raw.code.clone(), raw.start, raw.end);
            if causes.contains(&diagnostic) || remaining.contains(&key) {
                continue;
            }
            skipped.insert(diagnostic);
            let outputs = plan.outputs_by_diagnostic.get(&diagnostic);
            let mut redirect = output_causes(model, outputs, &poisoned);
            if redirect.is_empty() {
                redirect = causes.clone();
            }
            redirected.insert(diagnostic, redirect);
        }
    }
    let counts = unchecked_uses(request, &poisoned, &redirected);
    let mut kept: Vec<(usize, Option<String>)> = Vec::new();
    let mut owners: Vec<BindingOwner<'_>> = Vec::new();
    for (position, diagnostic) in request.diagnostics.iter().enumerate() {
        if skipped.contains(&diagnostic.id) {
            continue;
        }
        let count: usize = counts.get(&diagnostic.id).copied().unwrap_or_default();
        let note: Option<String> = (count > 0).then(|| {
            format!("{count} downstream output uses were not type-checked because of this error")
        });
        kept.push((position, note));
        owners.push(BindingOwner {
            code: &diagnostic.code,
            is_model: diagnostic.is_model,
            resource_name: diagnostic.resource_name.as_deref(),
        });
    }
    let mut models: Vec<(&str, HashSet<&str>)> = Vec::with_capacity(request.models.len());
    for model in &request.models {
        let codes: HashSet<&str> = model
            .bindings
            .iter()
            .map(|binding| binding.code.as_str())
            .collect();
        models.push((model.name.as_str(), codes));
    }
    TypeRecoveryOutcome {
        model_bindings: binding_positions(&models, &owners),
        kept,
    }
}

fn has_blocking_error(request: &TypeRecoveryRequest, failed: &[usize]) -> bool {
    for index in failed {
        if request.models[*index]
            .bindings
            .iter()
            .any(|binding| binding.is_error)
        {
            return true;
        }
    }
    false
}

fn failed_models(request: &TypeRecoveryRequest) -> Vec<usize> {
    request
        .models
        .iter()
        .enumerate()
        .filter(|(_, model)| !model.bindings.is_empty())
        .map(|(index, _)| index)
        .collect()
}

fn error_ids(request: &TypeRecoveryRequest) -> HashMap<usize, bool> {
    let mut errors: HashMap<usize, bool> = HashMap::new();
    for model in &request.models {
        for binding in &model.bindings {
            errors.insert(binding.id, binding.is_error);
        }
    }
    errors
}

/// Python's `_root_bindings`: pair repeated messages by occurrence.
fn root_bindings(model: &RecoveryModel) -> HashMap<usize, usize> {
    let mut pending: HashMap<(&str, &str), VecDeque<usize>> = HashMap::new();
    for binding in &model.bindings {
        pending
            .entry((binding.code.as_str(), binding.message.as_str()))
            .or_default()
            .push_back(binding.id);
    }
    let mut result: HashMap<usize, usize> = HashMap::new();
    for raw in &model.raw_bindings {
        if let Some(root) = pending
            .get_mut(&(raw.code.as_str(), raw.message.as_str()))
            .and_then(VecDeque::pop_front)
        {
            result.insert(raw.id, root);
        }
    }
    result
}

/// Python's `_column_at`: the only projection span that can contain `offset`.
fn column_at<'a>(
    columns: &'a [String],
    spans: &[(usize, usize)],
    starts: &[usize],
    offset: i64,
) -> Option<&'a String> {
    let reached: usize = match usize::try_from(offset) {
        Ok(offset) => starts.partition_point(|start| *start <= offset),
        Err(_) => 0,
    };
    let position = reached.checked_sub(1)?;
    let end: i64 = i64::try_from(spans[position].1).unwrap_or(i64::MAX);
    if offset >= end {
        return None;
    }
    columns.get(position)
}

fn reference_causes(model: &RecoveryModel, poisoned: &Poison) -> HashSet<usize> {
    let mut causes: HashSet<usize> = HashSet::new();
    for reference in &model.references {
        for ((name, _), root) in poisoned.entries() {
            if name == reference {
                causes.insert(root);
            }
        }
    }
    causes
}

/// Python's `_output_causes`: the poisoned inputs of the failing projection only.
fn output_causes(
    model: &RecoveryModel,
    outputs: Option<&HashSet<String>>,
    poisoned: &Poison,
) -> HashSet<usize> {
    let mut result: HashSet<usize> = HashSet::new();
    let Some(outputs) = outputs else {
        return result;
    };
    for output in &model.lineage {
        if outputs.contains(&output.output_column) {
            for (resource, column) in &output.upstream {
                if let Some(root) = poisoned.get(resource, column) {
                    result.insert(root);
                }
            }
        }
    }
    result
}

/// Python's `_unchecked_uses`: transitive unchecked output uses per retained root error.
fn unchecked_uses(
    request: &TypeRecoveryRequest,
    poisoned: &Poison,
    redirected: &HashMap<usize, HashSet<usize>>,
) -> HashMap<usize, usize> {
    let mut counts: HashMap<usize, usize> = HashMap::new();
    for model in &request.models {
        for output in &model.lineage {
            let mut pending: Vec<usize> = output
                .upstream
                .iter()
                .filter_map(|(resource, column)| poisoned.get(resource, column))
                .collect();
            let mut visited: HashSet<usize> = HashSet::new();
            while let Some(root) = pending.pop() {
                if !visited.insert(root) {
                    continue;
                }
                match redirected.get(&root) {
                    Some(targets) => pending.extend(targets.iter().copied()),
                    None => *counts.entry(root).or_default() += 1,
                }
            }
        }
    }
    counts
}
