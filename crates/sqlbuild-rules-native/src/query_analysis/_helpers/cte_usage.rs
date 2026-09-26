//! CTE liveness projected from the compiler's authoritative binding observations.

use std::collections::HashMap;

use polyglot_sql::expressions::Cte;
use polyglot_sql::scope::{Scope, build_scope};
use polyglot_sql::validation::binding_facts::{BindingOutput, OccurrenceBinding};
use polyglot_sql::{DialectType, Expression, ValidationSchema};

use crate::constants::{CTE_ROOT_SCOPE, CTE_USAGE_MAX_FUNCTION_DEPTH};
use crate::query_analysis::engine::StringInterner;
use crate::query_analysis::models::{CompactCteUsage, CteOutputSlot, CteSlotUsage, CteUsageBatch};

pub(crate) fn analyze_batch(payload: &str) -> Result<String, String> {
    let request: CteUsageBatch = serde_json::from_str(payload).map_err(|error| error.to_string())?;
    let results: Vec<Result<CompactCteUsage, String>> = request.requests.into_iter().map(|request| {
        let dialect: DialectType = request.dialect.parse().map_err(|error| format!("{error}"))?;
        let mut parsed = polyglot_sql::parse_with_options(&request.sql, dialect, &polyglot_sql::ParseOptions {
            complexity_guard: Some(polyglot_sql::ComplexityGuardOptions {
                max_function_call_depth: Some(CTE_USAGE_MAX_FUNCTION_DEPTH), ..Default::default()
            }),
        }).map_err(|error| error.to_string())?;
        if parsed.len() != 1 { return Err("CTE slot usage requires exactly one query".to_owned()); }
        let expression = parsed.pop().ok_or("CTE slot usage requires a query")?;
        analyze(&expression, request.schema.as_ref(), dialect).map(compact)
    }).collect();
    serde_json::to_string(&results).map_err(|error| error.to_string())
}

pub(crate) fn analyze(expression: &Expression, schema: Option<&ValidationSchema>, dialect: DialectType) -> Result<Vec<CteSlotUsage>, String> {
    analyze_with_exemptions(expression, schema, dialect, |_| false)
}

pub(crate) fn analyze_with_exemptions<F: Fn(&Cte) -> bool>(expression: &Expression, schema: Option<&ValidationSchema>, dialect: DialectType, exempt: F) -> Result<Vec<CteSlotUsage>, String> {
    let scope = build_scope(expression);
    let originals = cte_definitions(&scope, CTE_ROOT_SCOPE);
    if originals.is_empty() { return Ok(Vec::new()); }
    let empty = ValidationSchema { tables: Vec::new(), strict: Some(false) };
    let facts = polyglot_sql::validation::validate_parsed_with_binding_facts(
        vec![expression.clone()], dialect, schema.unwrap_or(&empty), &polyglot_sql::SchemaValidationOptions::default(),
    );
    let mut used: HashMap<(usize, usize), bool> = HashMap::new();
    for occurrence in &facts.occurrences {
        let required = facts.scopes.get(occurrence.scope_id).is_some_and(|scope| scope.kind == "SetOperation");
        for slot in read_slots(&occurrence.binding)? {
            if slot.0 != occurrence.scope_id { used.entry(slot).and_modify(|value| *value |= required).or_insert(required); }
        }
    }
    let exported = final_source(expression);
    let mut result: Vec<CteSlotUsage> = Vec::new();
    for scope in facts.scopes.iter().filter(|scope| scope.kind == "Cte") {
        let path = scope.path.replacen("statement[0]", CTE_ROOT_SCOPE, 1);
        let cte = originals.get(&path).ok_or("Binding facts changed the CTE scope structure")?;
        if exempt(cte) { continue; }
        let set_operation = matches!(query(&cte.this), Expression::Union(_) | Expression::Intersect(_) | Expression::Except(_));
        let distinct = matches!(query(&cte.this), Expression::Select(select) if select.distinct || select.distinct_on.is_some());
        let mut slots: Vec<CteOutputSlot> = Vec::new();
        for output in &scope.outputs {
            let BindingOutput::Slot { slot } = output else { return Err("CTE output slots are open; compiler input columns are required".to_owned()); };
            let read = used.get(&(slot.scope_id, slot.ordinal));
            slots.push(CteOutputSlot { name: slot.name.clone(), read: read.is_some(), semantically_required: set_operation || read.copied().unwrap_or(false) });
        }
        result.push(CteSlotUsage { scope: path, name: cte.alias.name.clone(), original: (*cte).clone(), slots, distinct, set_operation,
            model_output: scope.parent == Some(0) && exported.as_deref() == Some(&cte.alias.name),
        });
    }
    Ok(result)
}

fn read_slots(binding: &OccurrenceBinding) -> Result<Vec<(usize, usize)>, String> {
    match binding {
        OccurrenceBinding::OutputSlot { slot } => Ok(vec![(slot.scope_id, slot.ordinal)]),
        OccurrenceBinding::Merged { inputs } => {
            let mut slots: Vec<(usize, usize)> = Vec::new();
            for input in inputs { slots.extend(read_slots(input)?); }
            Ok(slots)
        }
        OccurrenceBinding::Unresolved { reason } => Err(format!("Unresolved compiler binding occurrence: {reason}")),
        OccurrenceBinding::Open { .. } => Err("Open compiler binding occurrence requires input schema".to_owned()),
        OccurrenceBinding::SourceColumn { source_kind: polyglot_sql::scope::SourceKind::Cte, .. } => Err("Compiler CTE binding is missing its output-slot identity".to_owned()),
        _ => Ok(Vec::new()),
    }
}

fn cte_definitions(scope: &Scope, path: &str) -> HashMap<String, Cte> {
    let mut definitions: HashMap<String, Cte> = HashMap::new();
    for (label, children) in [("ctes", &scope.cte_scopes), ("derived", &scope.derived_table_scopes), ("subqueries", &scope.subquery_scopes), ("lateral", &scope.udtf_scopes), ("branches", &scope.union_scopes)] {
        for (index, child) in children.iter().enumerate() {
            let child_path = format!("{path}.{label}[{index}]");
            if let Expression::Cte(cte) = &child.expression { definitions.insert(child_path.clone(), cte.as_ref().clone()); }
            definitions.extend(cte_definitions(child, &child_path));
        }
    }
    definitions
}

fn final_source(expression: &Expression) -> Option<String> {
    let Expression::Select(select) = query(expression) else { return None; };
    if select.expressions.len() != 1 || !matches!(&select.expressions[0], Expression::Star(_)) || !select.joins.is_empty() { return None; }
    let sources = &select.from.as_ref()?.expressions;
    if sources.len() != 1 { return None; }
    match &sources[0] { Expression::Table(table) if table.schema.is_none() && table.catalog.is_none() => Some(table.name.name.clone()), _ => None }
}

fn query(mut expression: &Expression) -> &Expression {
    loop { expression = match expression {
        Expression::Cte(cte) => &cte.this, Expression::Subquery(query) => &query.this,
        Expression::Paren(paren) => &paren.this, Expression::Annotated(annotated) => &annotated.this,
        _ => return expression,
    }; }
}

fn compact(ctes: Vec<CteSlotUsage>) -> CompactCteUsage {
    let mut result = CompactCteUsage { version: 1, strings: Vec::new(), ctes: Vec::new(), slots: Vec::new() };
    let mut interner = StringInterner::default();
    for (cte_index, cte) in ctes.into_iter().enumerate() {
        let scope = interner.intern(cte.scope);
        let name = interner.intern(cte.name);
        result.ctes.push((scope, name, cte.distinct, cte.set_operation, cte.model_output, !cte.original.columns.is_empty()));
        for (ordinal, slot) in cte.slots.into_iter().enumerate() {
            let name = interner.intern(slot.name);
            result.slots.push((cte_index, ordinal, name, slot.read, slot.semantically_required));
        }
    }
    result.strings = interner.strings;
    result
}
