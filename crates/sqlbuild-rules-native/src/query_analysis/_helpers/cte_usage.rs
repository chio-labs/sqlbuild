//! CTE liveness projected from the compiler's authoritative binding observations.

use std::collections::{HashMap, HashSet};

use polyglot_sql::expressions::Cte;
use polyglot_sql::scope::{Scope, build_scope_for_binding_facts as build_scope};
use polyglot_sql::validation::binding_facts::{BindingOutput, OccurrenceBinding};
use polyglot_sql::{DialectType, Expression, ValidationSchema};

use crate::constants::{
    CTE_DEFINITION_KIND, CTE_ROOT_SCOPE, CTE_SET_OPERATION_KIND, CTE_USAGE_MAX_FUNCTION_DEPTH,
};
use crate::query_analysis::engine::StringInterner;
use crate::query_analysis::models::{
    CompactCteUsage, CteBindingOptions, CteOutputSlot, CteSlotUsage, CteUsageBatch,
};

pub(crate) fn analyze_batch(payload: &str) -> Result<String, String> {
    let request: CteUsageBatch =
        serde_json::from_str(payload).map_err(|error| error.to_string())?;
    let results: Vec<Result<CompactCteUsage, String>> = request
        .requests
        .into_iter()
        .map(|request| {
            let dialect: DialectType = request
                .dialect
                .parse()
                .map_err(|error| format!("{error}"))?;
            let mut parsed = polyglot_sql::parse_with_options(
                &request.sql,
                dialect,
                &polyglot_sql::ParseOptions {
                    complexity_guard: Some(polyglot_sql::ComplexityGuardOptions {
                        max_function_call_depth: Some(CTE_USAGE_MAX_FUNCTION_DEPTH),
                        ..Default::default()
                    }),
                },
            )
            .map_err(|error| error.to_string())?;
            if parsed.len() != 1 {
                return Err("CTE slot usage requires exactly one query".to_owned());
            }
            let expression = parsed.pop().ok_or("CTE slot usage requires a query")?;
            analyze(&expression, request.schema.as_ref(), dialect).map(compact)
        })
        .collect();
    serde_json::to_string(&results).map_err(|error| error.to_string())
}

pub(crate) fn analyze(
    expression: &Expression,
    schema: Option<&ValidationSchema>,
    dialect: DialectType,
) -> Result<Vec<CteSlotUsage>, String> {
    analyze_with_exemptions(
        expression,
        CteBindingOptions {
            schema,
            dialect,
            quoted_ignore_case: false,
        },
        |_| false,
    )
}

pub(crate) fn analyze_with_exemptions<F: Fn(&Cte) -> bool>(
    expression: &Expression,
    options: CteBindingOptions<'_>,
    exempt: F,
) -> Result<Vec<CteSlotUsage>, String> {
    let scope = build_scope(expression);
    let originals = cte_definitions(&scope, CTE_ROOT_SCOPE);
    if originals.is_empty() || originals.values().all(&exempt) {
        return Ok(Vec::new());
    }
    let empty = ValidationSchema {
        tables: Vec::new(),
        strict: Some(false),
    };
    let facts = crate::semantic_validation::main::binding_occurrences(
        expression,
        options.schema.unwrap_or(&empty),
        options.dialect,
        options.quoted_ignore_case,
    )?;
    let mut used: HashMap<(usize, usize), bool> = HashMap::new();
    let mut local_reads: HashSet<(usize, usize)> = HashSet::new();
    for occurrence in &facts.occurrences {
        if matches!(occurrence.binding, OccurrenceBinding::Unresolved { .. })
            && occurrence.span.is_some_and(|span| {
                facts.validation.errors.iter().any(|error| {
                    error.code == polyglot_sql::validation::validation_codes::E_UNKNOWN_COLUMN
                        && error.severity == polyglot_sql::ValidationSeverity::Error
                        && error.start.is_some_and(|start| start >= span.start)
                        && error.end.is_some_and(|end| end <= span.end)
                })
            })
        {
            continue;
        }
        let required = facts
            .scopes
            .get(occurrence.scope_id)
            .is_some_and(|scope| scope.kind == CTE_SET_OPERATION_KIND);
        for slot in read_slots(&occurrence.binding)? {
            if slot.0 == occurrence.scope_id {
                local_reads.insert(slot);
                continue;
            }
            used.entry(slot)
                .and_modify(|value| *value |= required)
                .or_insert(required);
        }
    }
    let exported = final_source(expression);
    let mut result: Vec<CteSlotUsage> = Vec::new();
    for scope in facts
        .scopes
        .iter()
        .filter(|scope| scope.kind == CTE_DEFINITION_KIND)
    {
        let path = scope.path.replacen("statement[0]", CTE_ROOT_SCOPE, 1);
        let cte = originals
            .get(&path)
            .ok_or("Binding facts changed the CTE scope structure")?;
        if exempt(cte) {
            continue;
        }
        let set_operation = matches!(
            query(&cte.this),
            Expression::Union(_) | Expression::Intersect(_) | Expression::Except(_)
        );
        let distinct = matches!(query(&cte.this), Expression::Select(select) if select.distinct || select.distinct_on.is_some());
        let mut slots: Vec<CteOutputSlot> = Vec::new();
        for output in &scope.outputs {
            let BindingOutput::Slot { slot } = output else {
                slots.push(CteOutputSlot {
                    locally_read: false,
                    name: "*".to_owned(),
                    read: true,
                    semantically_required: true,
                });
                continue;
            };
            let read = used.get(&(slot.scope_id, slot.ordinal));
            slots.push(CteOutputSlot {
                locally_read: local_reads.contains(&(slot.scope_id, slot.ordinal)),
                name: slot.name.clone(),
                read: read.is_some(),
                semantically_required: set_operation || read.copied().unwrap_or(false),
            });
        }
        result.push(CteSlotUsage {
            partially_checked: scope.partially_checked,
            scope: path,
            name: cte.alias.name.clone(),
            original: (*cte).clone(),
            slots,
            distinct,
            set_operation,
            model_output: scope.parent == Some(0) && exported.as_deref() == Some(&cte.alias.name),
        });
    }
    Ok(result)
}

fn read_slots(binding: &OccurrenceBinding) -> Result<Vec<(usize, usize)>, String> {
    match binding {
        OccurrenceBinding::OutputSlot { slot } => Ok(vec![(slot.scope_id, slot.ordinal)]),
        OccurrenceBinding::Merged { inputs }
        | OccurrenceBinding::Partial { candidates: inputs } => {
            let mut slots: Vec<(usize, usize)> = Vec::new();
            for input in inputs {
                slots.extend(read_slots(input)?);
            }
            Ok(slots)
        }
        OccurrenceBinding::Unresolved { reason } => {
            Err(format!("Unresolved compiler binding occurrence: {reason}"))
        }
        OccurrenceBinding::Open { .. } | OccurrenceBinding::OpenSourceColumn { .. } => {
            Ok(Vec::new())
        }
        OccurrenceBinding::SourceColumn {
            source_kind: polyglot_sql::scope::SourceKind::Cte,
            ..
        } => Err("Compiler CTE binding is missing its output-slot identity".to_owned()),
        _ => Ok(Vec::new()),
    }
}

fn cte_definitions(scope: &Scope, path: &str) -> HashMap<String, Cte> {
    let mut definitions: HashMap<String, Cte> = HashMap::new();
    for (label, children) in [
        ("ctes", &scope.cte_scopes),
        ("derived", &scope.derived_table_scopes),
        ("subqueries", &scope.subquery_scopes),
        ("lateral", &scope.udtf_scopes),
        ("branches", &scope.union_scopes),
    ] {
        for (index, child) in children.iter().enumerate() {
            let child_path = format!("{path}.{label}[{index}]");
            if let Expression::Cte(cte) = &child.expression {
                definitions.insert(child_path.clone(), cte.as_ref().clone());
            }
            definitions.extend(cte_definitions(child, &child_path));
        }
    }
    definitions
}

fn final_source(expression: &Expression) -> Option<String> {
    let Expression::Select(select) = query(expression) else {
        return None;
    };
    if select.expressions.len() != 1
        || !matches!(&select.expressions[0], Expression::Star(_))
        || !select.joins.is_empty()
    {
        return None;
    }
    let sources = &select.from.as_ref()?.expressions;
    if sources.len() != 1 {
        return None;
    }
    match &sources[0] {
        Expression::Table(table) if table.schema.is_none() && table.catalog.is_none() => {
            Some(table.name.name.clone())
        }
        _ => None,
    }
}

fn query(mut expression: &Expression) -> &Expression {
    loop {
        expression = match expression {
            Expression::Cte(cte) => &cte.this,
            Expression::Subquery(query) => &query.this,
            Expression::Paren(paren) => &paren.this,
            Expression::Annotated(annotated) => &annotated.this,
            _ => return expression,
        };
    }
}

fn compact(ctes: Vec<CteSlotUsage>) -> CompactCteUsage {
    let mut result = CompactCteUsage {
        local_reads: Vec::new(),
        partial_ctes: Vec::new(),
        version: 1,
        strings: Vec::new(),
        ctes: Vec::new(),
        slots: Vec::new(),
    };
    let mut interner = StringInterner::default();
    for (cte_index, cte) in ctes.into_iter().enumerate() {
        if cte.partially_checked {
            result.partial_ctes.push(cte_index);
        }
        let scope = interner.intern(cte.scope);
        let name = interner.intern(cte.name);
        result.ctes.push((
            scope,
            name,
            cte.distinct,
            cte.set_operation,
            cte.model_output,
            !cte.original.columns.is_empty(),
        ));
        for (ordinal, slot) in cte.slots.into_iter().enumerate() {
            if slot.locally_read {
                result.local_reads.push((cte_index, ordinal));
            }
            let name = interner.intern(slot.name);
            result.slots.push((
                cte_index,
                ordinal,
                name,
                slot.read,
                slot.semantically_required,
            ));
        }
    }
    result.strings = interner.strings;
    result
}
