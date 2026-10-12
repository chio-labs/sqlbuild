//! The column-read walk over one query and the queries nested inside it.

use std::rc::Rc;

use polyglot_sql::Expression;
use serde_json::{Map, Value};
use sqlbuild_core::text::main::python_casefold::python_casefold;

use crate::required_columns::_helpers::payload::{
    arg, column_refs_in_payload, payload_name, plain_value,
};
use crate::required_columns::_helpers::relations::{
    RelationMap, RelationReads, either, unique_reads, unique_resources,
};
use crate::required_columns::_helpers::tree::{
    alias_or_name, children, is_star, kind, payload, set_operation, top_level_ctes,
    unwrap_annotations,
};
use crate::required_columns::constants::{
    CLAUSE_NAMES, KIND_COLUMN, KIND_SELECT, KIND_SUBQUERY, KIND_TABLE,
    OUTPUT_ALIAS_FALLBACK_CLAUSES, OUTPUT_ALIAS_FIRST_CLAUSES, SET_OPERATION_KINDS,
};
use crate::required_columns::models::ColumnRead;

/// Each `JOIN ... USING` column's reads, by casefolded name, in first-joined order.
type SharedReads = Vec<(String, Vec<ColumnRead>)>;
/// Named output columns and the reads each stands for.
type Slots = Vec<(String, Vec<ColumnRead>)>;

/// The relations one select's column names resolve against.
struct Scope<'a> {
    local: &'a RelationMap,
    outer: &'a RelationMap,
    shared: &'a SharedReads,
}

fn shared_get<'a>(shared: &'a SharedReads, name: &str) -> Option<&'a Vec<ColumnRead>> {
    shared
        .iter()
        .find(|(key, _)| key == name)
        .map(|(_, reads)| reads)
}

fn is_set_operation(kind_name: &str) -> bool {
    SET_OPERATION_KINDS.contains(&kind_name)
}

/// `_resolve_query_reads`: a query's output relation and the external columns it reads.
pub(crate) fn query_reads(
    query: &Expression,
    inherited: &RelationMap,
    outer: &RelationMap,
) -> (RelationReads, Vec<ColumnRead>) {
    let query: &Expression = unwrap_annotations(query);
    let mut relations: RelationMap = inherited.clone();
    let mut required: Vec<ColumnRead> = Vec::new();
    for (cte_name, body, has_column_aliases) in top_level_ctes(query) {
        let (mut cte_reads, cte_required) = query_reads(body, &relations, outer);
        required.extend(cte_required);
        if has_column_aliases {
            cte_reads = cte_column_aliases(query, cte_name, &cte_reads);
        }
        relations.insert(python_casefold(cte_name), Rc::new(cte_reads));
    }
    let query_kind: &str = kind(query);
    if is_set_operation(query_kind) {
        let (reads, set_required) = set_operation_reads(query, &relations, outer);
        required.extend(set_required);
        return (reads, unique_reads(required));
    }
    if query_kind != KIND_SELECT {
        return (RelationReads::default(), unique_reads(required));
    }
    let mut local: RelationMap = select_tables(query, &relations);
    let mut nested_required: Vec<ColumnRead> = Vec::new();
    for (nested, alias) in direct_nested_queries(query) {
        let (nested_reads, reads) = query_reads(nested, &relations, &outer.merged(&local));
        nested_required.extend(reads);
        if !alias.is_empty() {
            local.insert(python_casefold(alias), Rc::new(nested_reads));
        }
    }
    let shared: SharedReads = join_using_column_reads(query, &local);
    let scope: Scope<'_> = Scope {
        local: &local,
        outer,
        shared: &shared,
    };
    let (slots, passthrough, projection_required) = projection_slots(query, &scope);
    required.extend(clause_reads(query, &slots, &scope));
    for (_, reads) in &shared {
        required.extend(reads.iter().cloned());
    }
    for (_, slot) in &slots {
        required.extend(slot.iter().cloned());
    }
    required.extend(projection_required);
    required.extend(nested_required);
    let relation: RelationReads = RelationReads {
        slots,
        passthrough: unique_resources(passthrough),
    };
    (relation, unique_reads(required))
}

/// Each direct table the select reads that resolves to a known relation, by name and alias.
fn select_tables(query: &Expression, relations: &RelationMap) -> RelationMap {
    let mut local: RelationMap = RelationMap::default();
    for table in children(query) {
        if kind(table) != KIND_TABLE {
            continue;
        }
        let name: String = python_casefold(table.get_name());
        let Some(relation) = relations.get(&name) else {
            continue;
        };
        let relation: Rc<RelationReads> = Rc::clone(relation);
        local.insert(name, Rc::clone(&relation));
        let alias: &str = alias_or_name(table);
        if !alias.is_empty() {
            local.insert(python_casefold(alias), relation);
        }
    }
    local
}

/// The select's output slots, passthrough resources and projection reads.
fn projection_slots(
    query: &Expression,
    scope: &Scope<'_>,
) -> (Slots, Vec<(String, String)>, Vec<ColumnRead>) {
    let mut slots: Slots = Vec::new();
    let mut passthrough: Vec<(String, String)> = Vec::new();
    let mut projection_required: Vec<ColumnRead> = Vec::new();
    for raw in query.get_expressions() {
        let projection: &Expression = unwrap_annotations(raw);
        if is_star(projection) {
            for relation in star_relations(projection, scope.local) {
                slots.extend(relation.slots.iter().cloned());
                passthrough.extend(relation.passthrough.iter().cloned());
            }
            slots.extend(star_modifier_slots(projection, scope));
            continue;
        }
        let output_name: &str = projection.get_output_name();
        let leaves: Vec<ColumnRead> = expression_reads(projection, scope);
        projection_required.extend(leaves.iter().cloned());
        if !output_name.is_empty() {
            slots.push((output_name.to_owned(), leaves));
        }
    }
    (slots, passthrough, projection_required)
}

/// `_resolve_set_operation_reads`.
fn set_operation_reads(
    operation: &Expression,
    inherited: &RelationMap,
    outer: &RelationMap,
) -> (RelationReads, Vec<ColumnRead>) {
    let Some((left, right, by_name)) = set_operation(operation) else {
        return (RelationReads::default(), Vec::new());
    };
    let (left, mut required) = query_reads(left, inherited, outer);
    let (right, right_required) = query_reads(right, inherited, outer);
    required.extend(right_required);
    let slots: Slots = if by_name {
        by_name_slots(&left.slots, &right.slots)
    } else if left.slots.len() == right.slots.len() {
        left.slots
            .iter()
            .zip(&right.slots)
            .map(|((name, left_leaves), (_, right_leaves))| {
                (name.clone(), combined(left_leaves, right_leaves))
            })
            .collect()
    } else {
        Vec::new()
    };
    let mut passthrough: Vec<(String, String)> = left.passthrough.clone();
    passthrough.extend(right.passthrough.iter().cloned());
    let relation: RelationReads = RelationReads {
        slots,
        passthrough: unique_resources(passthrough),
    };
    (relation, unique_reads(required))
}

/// A `BY NAME` set operation's slots: each left column with the right column of its name.
fn by_name_slots(left: &Slots, right: &Slots) -> Slots {
    let mut right_by_name: Vec<(String, &Vec<ColumnRead>)> = Vec::new();
    for (name, leaves) in right {
        let key: String = python_casefold(name);
        match right_by_name
            .iter_mut()
            .find(|(existing, _)| *existing == key)
        {
            Some(entry) => entry.1 = leaves,
            None => right_by_name.push((key, leaves)),
        }
    }
    let mut slots: Slots = Vec::with_capacity(left.len());
    for (name, leaves) in left {
        let key: String = python_casefold(name);
        let empty: Vec<ColumnRead> = Vec::new();
        let right_leaves: &Vec<ColumnRead> = right_by_name
            .iter()
            .find(|(existing, _)| *existing == key)
            .map_or(&empty, |(_, leaves)| leaves);
        slots.push((name.clone(), combined(leaves, right_leaves)));
    }
    slots
}

fn combined(left: &[ColumnRead], right: &[ColumnRead]) -> Vec<ColumnRead> {
    let mut reads: Vec<ColumnRead> = left.to_vec();
    reads.extend(right.iter().cloned());
    unique_reads(reads)
}

/// `_resolve_expression_reads`.
fn expression_reads(expression: &Expression, scope: &Scope<'_>) -> Vec<ColumnRead> {
    let mut resolved: Vec<ColumnRead> = Vec::new();
    for (column_name, table_name) in direct_column_refs(expression) {
        if column_name.is_empty() {
            continue;
        }
        if !table_name.is_empty() {
            if let Some(relation) = either(scope.local, scope.outer, &table_name) {
                resolved.extend(relation.resolve(&column_name));
            }
            continue;
        }
        resolved.extend(unqualified_column(&column_name, scope).1);
    }
    unique_reads(resolved)
}

/// `_resolve_clause_reads`.
fn clause_reads(select: &Expression, output_slots: &Slots, scope: &Scope<'_>) -> Vec<ColumnRead> {
    let mut resolved: Vec<ColumnRead> = Vec::new();
    let mut select_args: Map<String, Value> = payload(select);
    for clause_name in CLAUSE_NAMES {
        let payload: Option<Value> = plain_value(select_args.remove(clause_name));
        for (column_name, table_name) in column_refs_in_payload(payload.as_ref()) {
            if column_name.is_empty() {
                continue;
            }
            if !table_name.is_empty() {
                if let Some(relation) = either(scope.local, scope.outer, &table_name) {
                    resolved.extend(relation.resolve(&column_name));
                }
                continue;
            }
            let output_match: Option<&Vec<ColumnRead>> = output_slot(&column_name, output_slots);
            if let Some(leaves) = output_match
                && OUTPUT_ALIAS_FIRST_CLAUSES.contains(&clause_name)
            {
                resolved.extend(leaves.iter().cloned());
                continue;
            }
            let (input_present, input_reads) = unqualified_column(&column_name, scope);
            if input_present {
                resolved.extend(input_reads);
                continue;
            }
            if let Some(leaves) = output_match
                && OUTPUT_ALIAS_FALLBACK_CLAUSES.contains(&clause_name)
            {
                resolved.extend(leaves.iter().cloned());
            }
        }
    }
    unique_reads(resolved)
}

/// `_output_slot_reads`: the last output slot named `column_name`.
fn output_slot<'a>(column_name: &str, output_slots: &'a Slots) -> Option<&'a Vec<ColumnRead>> {
    let normalized: String = python_casefold(column_name);
    output_slots
        .iter()
        .rev()
        .find(|(name, _)| python_casefold(name) == normalized)
        .map(|(_, leaves)| leaves)
}

/// `_star_modifier_slots`: slots a star's `REPLACE` and `RENAME` modifiers add.
fn star_modifier_slots(projection: &Expression, scope: &Scope<'_>) -> Slots {
    let mut slots: Slots = Vec::new();
    let expressions: Vec<&Expression> = children(projection);
    if let Some(Value::Array(replacements)) = arg(projection, "replace")
        && replacements.len() == expressions.len()
    {
        for (replacement, expression) in replacements.iter().zip(expressions) {
            let Some(replacement) = replacement.as_object() else {
                continue;
            };
            let output_name: String = payload_name(replacement.get("alias"));
            if output_name.is_empty() {
                continue;
            }
            slots.push((output_name, expression_reads(expression, scope)));
        }
    }
    if let Some(Value::Array(renames)) = arg(projection, "rename") {
        for rename in &renames {
            let Some([input, output]) = rename.as_array().map(Vec::as_slice) else {
                continue;
            };
            let input_name: String = payload_name(Some(input));
            let output_name: String = payload_name(Some(output));
            if input_name.is_empty() || output_name.is_empty() {
                continue;
            }
            slots.push((output_name, unqualified_column(&input_name, scope).1));
        }
    }
    slots
}

/// `_resolve_unqualified_column_with_presence`.
fn unqualified_column(column_name: &str, scope: &Scope<'_>) -> (bool, Vec<ColumnRead>) {
    if let Some(reads) = shared_get(scope.shared, &python_casefold(column_name)) {
        return (true, reads.clone());
    }
    let local: Vec<Vec<ColumnRead>> = present_candidates(scope.local, column_name);
    match local.len() {
        1 => return (true, local.into_iter().next().unwrap_or_default()),
        0 => {}
        _ => return (true, Vec::new()),
    }
    let mut outer: Vec<Vec<ColumnRead>> = present_candidates(scope.outer, column_name);
    if outer.len() == 1 {
        return (true, outer.remove(0));
    }
    (!outer.is_empty(), Vec::new())
}

/// The reads of each distinct relation that has `column_name`.
fn present_candidates(relations: &RelationMap, column_name: &str) -> Vec<Vec<ColumnRead>> {
    let mut candidates: Vec<Vec<ColumnRead>> = Vec::new();
    for relation in relations.unique() {
        let (present, leaves) = relation.resolve_with_presence(column_name);
        if present {
            candidates.push(leaves);
        }
    }
    candidates
}

/// `_join_using_column_reads`.
fn join_using_column_reads(select: &Expression, local: &RelationMap) -> SharedReads {
    let Some(Value::Array(joins)) = arg(select, "joins") else {
        return Vec::new();
    };
    let sequence: Vec<Rc<RelationReads>> = joined_relation_sequence(select, local);
    let Some(first) = sequence.first() else {
        return Vec::new();
    };
    let mut joined: Vec<Rc<RelationReads>> = vec![Rc::clone(first)];
    let mut joined_shared: SharedReads = Vec::new();
    let mut by_column: SharedReads = Vec::new();
    for (index, join) in (1..).zip(&joins) {
        let Some(join) = join.as_object() else {
            continue;
        };
        if index >= sequence.len() {
            break;
        }
        let right: &Rc<RelationReads> = &sequence[index];
        if let Some(Value::Array(columns)) = join.get("using") {
            for column in columns {
                let name: String = payload_name(Some(column));
                if name.is_empty() {
                    continue;
                }
                let key: String = python_casefold(&name);
                let combined_reads: Vec<ColumnRead> =
                    using_column_reads(&name, &joined, right, shared_get(&joined_shared, &key));
                match joined_shared
                    .iter_mut()
                    .find(|(existing, _)| *existing == key)
                {
                    Some(entry) => entry.1 = combined_reads.clone(),
                    None => joined_shared.push((key.clone(), combined_reads.clone())),
                }
                match by_column.iter_mut().find(|(existing, _)| *existing == key) {
                    Some(entry) => entry.1.extend(combined_reads),
                    None => by_column.push((key, combined_reads)),
                }
            }
        }
        joined.push(Rc::clone(right));
    }
    by_column
        .into_iter()
        .map(|(name, reads)| (name, unique_reads(reads)))
        .collect()
}

/// One `USING` column's reads: the joined side's, unless ambiguous, then the right side's.
fn using_column_reads(
    name: &str,
    joined: &[Rc<RelationReads>],
    right: &RelationReads,
    left_shared: Option<&Vec<ColumnRead>>,
) -> Vec<ColumnRead> {
    let left: Vec<ColumnRead> = match left_shared {
        Some(reads) => reads.clone(),
        None => {
            let mut candidates: Vec<Vec<ColumnRead>> = Vec::new();
            for relation in joined {
                let (present, leaves) = relation.resolve_with_presence(name);
                if present {
                    candidates.push(leaves);
                }
            }
            if candidates.len() == 1 {
                candidates.remove(0)
            } else {
                Vec::new()
            }
        }
    };
    combined(&left, &right.resolve_with_presence(name).1)
}

/// The known relations of the select's direct tables and subqueries, in tree order.
fn joined_relation_sequence(select: &Expression, local: &RelationMap) -> Vec<Rc<RelationReads>> {
    let mut sequence: Vec<Rc<RelationReads>> = Vec::new();
    for child in children(select) {
        let name: &str = match kind(child) {
            KIND_TABLE => child.get_name(),
            KIND_SUBQUERY => alias_or_name(child),
            _ => continue,
        };
        if let Some(relation) = local.get(&python_casefold(name)) {
            sequence.push(Rc::clone(relation));
        }
    }
    sequence
}

/// `_direct_column_refs`: `(column, table)` of each column outside nested queries.
fn direct_column_refs(expression: &Expression) -> Vec<(String, String)> {
    let expression_kind: &str = kind(expression);
    if expression_kind == KIND_COLUMN {
        let table: Option<Value> = arg(expression, "table");
        let table_name: String = payload_name(table.as_ref());
        return vec![(expression.get_name().to_owned(), table_name)];
    }
    if expression_kind == KIND_SUBQUERY
        || expression_kind == KIND_SELECT
        || is_set_operation(expression_kind)
    {
        return Vec::new();
    }
    children(expression)
        .into_iter()
        .flat_map(direct_column_refs)
        .collect()
}

/// `_direct_nested_queries`: each query nested in the select outside its tables, and its alias.
fn direct_nested_queries(select: &Expression) -> Vec<(&Expression, &str)> {
    children(select)
        .into_iter()
        .filter(|child| kind(child) != KIND_TABLE)
        .flat_map(nested_queries)
        .collect()
}

fn nested_queries(expression: &Expression) -> Vec<(&Expression, &str)> {
    let expression_kind: &str = kind(expression);
    if expression_kind == KIND_SUBQUERY {
        return expression
            .get_this()
            .map(|body| vec![(body, alias_or_name(expression))])
            .unwrap_or_default();
    }
    if expression_kind == KIND_SELECT || is_set_operation(expression_kind) {
        return vec![(expression, "")];
    }
    children(expression)
        .into_iter()
        .flat_map(nested_queries)
        .collect()
}

/// `_star_projection_relations`: the star's qualified relation, else every local relation.
fn star_relations(projection: &Expression, local: &RelationMap) -> Vec<Rc<RelationReads>> {
    let table: Option<Value> = arg(projection, "table");
    let table_name: String = payload_name(table.as_ref());
    if table_name.is_empty() {
        return local.unique();
    }
    local
        .get(&python_casefold(&table_name))
        .map(|relation| vec![Rc::clone(relation)])
        .unwrap_or_default()
}

/// `_apply_cte_column_aliases`: a CTE's slots renamed by its column alias list.
fn cte_column_aliases(query: &Expression, cte_name: &str, reads: &RelationReads) -> RelationReads {
    let aliases: Vec<String> = cte_alias_names(query, cte_name);
    if aliases.len() != reads.slots.len() {
        return RelationReads::default();
    }
    RelationReads {
        slots: aliases
            .into_iter()
            .zip(&reads.slots)
            .map(|(alias, (_, leaves))| (alias, leaves.clone()))
            .collect(),
        passthrough: Vec::new(),
    }
}

/// The column alias list of the first CTE payload named `cte_name`.
fn cte_alias_names(query: &Expression, cte_name: &str) -> Vec<String> {
    let Some(Value::Object(with)) = arg(query, "with") else {
        return Vec::new();
    };
    let Some(Value::Array(ctes)) = with.get("ctes") else {
        return Vec::new();
    };
    for cte in ctes.iter().filter_map(Value::as_object) {
        let Some(Value::Object(alias)) = cte.get("alias") else {
            continue;
        };
        if alias.get("name").and_then(Value::as_str) != Some(cte_name) {
            continue;
        }
        let Some(Value::Array(columns)) = cte.get("columns") else {
            return Vec::new();
        };
        return columns
            .iter()
            .filter_map(|column| column.get("name").and_then(Value::as_str))
            .map(str::to_owned)
            .collect();
    }
    Vec::new()
}
