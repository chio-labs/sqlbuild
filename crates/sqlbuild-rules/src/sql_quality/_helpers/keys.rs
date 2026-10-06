//! Unique-key propagation through one model's relations, for ranking determinism proofs.

use std::collections::HashMap;

use polyglot_sql::Expression;
use polyglot_sql::expressions::{JoinKind, Literal, Select};

use crate::sql_quality::constants::FIRST_ROW;
use crate::sql_quality::models::QualityRequest;
use crate::sql_quality::syntax::{Projection, columns, lower, projections, qualifier, sources};
use crate::sql_quality::types::{InputKey, Keys};

/// Keys known for relations by name: declared upstream keys and earlier CTE outputs.
pub(crate) struct KeyEnvironment {
    pub(crate) declared: HashMap<String, Keys>,
    pub(crate) ctes: HashMap<String, Keys>,
    /// Per CTE, `(row number output, partition output columns)` for deduplication filters.
    pub(crate) row_numbers: HashMap<String, Vec<(String, Vec<String>)>>,
}

impl KeyEnvironment {
    /// Output keys of a query expression, by output column name.
    pub(crate) fn query_keys(&self, expression: &Expression) -> Keys {
        match expression {
            Expression::Select(select) => self.select_keys(select),
            Expression::Subquery(subquery) => self.query_keys(&subquery.this),
            Expression::Paren(paren) => self.query_keys(&paren.this),
            Expression::Union(union) if !union.all => all_columns_key(&union.left),
            Expression::Intersect(intersect) => self.query_keys(&intersect.left),
            Expression::Except(except) => self.query_keys(&except.left),
            _ => Vec::new(),
        }
    }

    fn relation_keys(&self, relation: &Expression) -> Keys {
        match relation {
            Expression::Table(table) => {
                let name: String = lower(&table.name.name);
                self.ctes
                    .get(&name)
                    .cloned()
                    .or_else(|| self.declared.get(&name).cloned())
                    .unwrap_or_default()
            }
            Expression::Subquery(subquery) => self.query_keys(&subquery.this),
            _ => Vec::new(),
        }
    }

    /// Keys of a select's joined and filtered input rows, before projection.
    pub(crate) fn input_keys(&self, select: &Select) -> Vec<InputKey> {
        if select
            .from
            .as_ref()
            .is_none_or(|from| from.expressions.len() != 1)
        {
            return Vec::new();
        }
        let found: Vec<(String, Option<String>, &Expression)> = sources(select);
        let Some((first_alias, _, first)) = found.first() else {
            return Vec::new();
        };
        let mut keys: Vec<InputKey> = qualify(first_alias, self.relation_keys(first));
        keys.extend(qualify(first_alias, self.deduplicated_keys(select, first)));
        for (join, (alias, _, relation)) in select.joins.iter().zip(found.iter().skip(1)) {
            let right: Vec<InputKey> = qualify(alias, self.relation_keys(relation));
            let equated: Vec<(String, String)> = join_equalities(join, alias);
            let left_columns: Vec<&str> = equated.iter().map(|(_, left)| left.as_str()).collect();
            let right_columns: Vec<&str> =
                equated.iter().map(|(right, _)| right.as_str()).collect();
            let left_unique: bool = keys.iter().any(|key| key_within(key, &left_columns));
            let right_unique: bool = right.iter().any(|key| key_within(key, &right_columns));
            let mut joined: Vec<InputKey> = Vec::new();
            if right_unique
                && !matches!(
                    join.kind,
                    JoinKind::Right | JoinKind::Full | JoinKind::Cross
                )
            {
                joined.extend(keys.iter().cloned());
            }
            if left_unique && matches!(join.kind, JoinKind::Inner | JoinKind::Right) {
                joined.extend(right.iter().cloned());
            }
            keys = joined;
        }
        keys
    }

    /// Input keys plus a `QUALIFY ROW_NUMBER() ... = n` partition, which holds only for output rows.
    fn filtered_input_keys(&self, select: &Select) -> Vec<InputKey> {
        let mut keys: Vec<InputKey> = self.input_keys(select);
        if let Some(qualify_clause) = &select.qualify {
            keys.extend(qualified_rank_keys(&qualify_clause.this, &sources(select)));
        }
        keys
    }

    /// Partition keys of a `ROW_NUMBER()` output that this select filters to `= 1`.
    fn deduplicated_keys(&self, select: &Select, relation: &Expression) -> Keys {
        let Expression::Table(table) = relation else {
            return Vec::new();
        };
        let Some(ranks) = self.row_numbers.get(&lower(&table.name.name)) else {
            return Vec::new();
        };
        let filtered: Vec<String> = select
            .where_clause
            .as_ref()
            .map(|clause| first_row_filters(&clause.this))
            .unwrap_or_default();
        ranks
            .iter()
            .filter(|(rank, _)| filtered.contains(rank))
            .map(|(_, key)| key.clone())
            .collect()
    }

    fn select_keys(&self, select: &Select) -> Keys {
        let output: Vec<Projection<'_>> = projections(select);
        let mut keys: Keys = Vec::new();
        if select.distinct
            && output
                .iter()
                .all(|item| matches!(item, Projection::Named { .. }))
        {
            keys.push(output_names(&output));
        }
        if let Some(group_by) = &select.group_by
            && group_by.all.is_none()
            && let Some(grain) = output_key_of(&group_by.expressions, &output)
        {
            keys.push(grain);
            return keys;
        }
        let star: bool = output
            .iter()
            .any(|item| matches!(item, Projection::Star(_)));
        for input in self.filtered_input_keys(select) {
            if let Some(key) = project_key(&input, &output, star) {
                keys.push(key);
            }
        }
        keys
    }
}

fn qualify(alias: &str, keys: Keys) -> Vec<InputKey> {
    keys.into_iter()
        .map(|key| qualified_key(alias, key))
        .collect()
}

fn qualified_key(alias: &str, key: Vec<String>) -> InputKey {
    key.into_iter()
        .map(|column| (alias.to_owned(), column))
        .collect()
}

fn key_within(key: &InputKey, columns: &[&str]) -> bool {
    key.iter()
        .all(|(_, column)| columns.contains(&column.as_str()))
}

/// `(right column, left column)` pairs equated by a join's ON or USING condition.
fn join_equalities(
    join: &polyglot_sql::expressions::Join,
    right_alias: &str,
) -> Vec<(String, String)> {
    let mut pairs: Vec<(String, String)> = join
        .using
        .iter()
        .map(|identifier| (lower(&identifier.name), lower(&identifier.name)))
        .collect();
    let mut pending: Vec<&Expression> = join.on.iter().collect();
    while let Some(expression) = pending.pop() {
        match expression {
            Expression::And(operation) => {
                pending.push(&operation.left);
                pending.push(&operation.right);
            }
            Expression::Paren(paren) => pending.push(&paren.this),
            Expression::Eq(operation) => {
                if let (Expression::Column(left), Expression::Column(right)) =
                    (&operation.left, &operation.right)
                {
                    let (inner, outer) = if qualifier(left).as_deref() == Some(right_alias) {
                        (left, right)
                    } else {
                        (right, left)
                    };
                    pairs.push((lower(&inner.name.name), lower(&outer.name.name)));
                }
            }
            _ => {}
        }
    }
    pairs
}

fn qualified_rank_keys(
    condition: &Expression,
    found: &[(String, Option<String>, &Expression)],
) -> Vec<InputKey> {
    let Expression::Eq(operation) = condition else {
        return Vec::new();
    };
    let window = match (&operation.left, &operation.right) {
        (Expression::WindowFunction(window), Expression::Literal(_))
        | (Expression::Literal(_), Expression::WindowFunction(window)) => window,
        _ => return Vec::new(),
    };
    if !matches!(window.this, Expression::RowNumber(_)) || window.over.partition_by.is_empty() {
        return Vec::new();
    }
    let mut key: InputKey = InputKey::new();
    for expression in &window.over.partition_by {
        let Expression::Column(column) = expression else {
            return Vec::new();
        };
        let alias: String = qualifier(column)
            .or_else(|| (found.len() == 1).then(|| found[0].0.clone()))
            .unwrap_or_default();
        key.insert((alias, lower(&column.name.name)));
    }
    vec![key]
}

fn output_names(output: &[Projection<'_>]) -> Vec<String> {
    output
        .iter()
        .filter_map(|item| match item {
            Projection::Named { name, .. } => Some(name.clone()),
            _ => None,
        })
        .collect()
}

fn output_key_of(expressions: &[Expression], output: &[Projection<'_>]) -> Option<Vec<String>> {
    let mut key: Vec<String> = Vec::new();
    for expression in expressions {
        if let Expression::Literal(literal) = expression
            && let Literal::Number(text) = literal.as_ref()
        {
            let Ok(ordinal) = text.parse::<usize>() else {
                return None;
            };
            let Some(Projection::Named { name, .. }) = ordinal
                .checked_sub(1)
                .and_then(|position| output.get(position))
            else {
                return None;
            };
            key.push(name.clone());
            continue;
        }
        let Expression::Column(column) = expression else {
            return None;
        };
        let name: String = lower(&column.name.name);
        let projected: Option<String> = output.iter().find_map(|item| match item {
            Projection::Named {
                name: output_name,
                expression: Expression::Column(source),
            } if lower(&source.name.name) == name => Some(output_name.clone()),
            Projection::Named {
                name: output_name, ..
            } if *output_name == name => Some(output_name.clone()),
            _ => None,
        });
        key.push(projected?);
    }
    Some(key)
}

fn project_key(input: &InputKey, output: &[Projection<'_>], star: bool) -> Option<Vec<String>> {
    let mut key: Vec<String> = Vec::new();
    for (alias, column) in input {
        let projected: Option<String> = output.iter().find_map(|item| match item {
            Projection::Named {
                name,
                expression: Expression::Column(source),
            } if lower(&source.name.name) == *column
                && qualifier(source).is_none_or(|table| table == *alias) =>
            {
                Some(name.clone())
            }
            Projection::Star(star)
                if star
                    .table
                    .as_ref()
                    .is_none_or(|table| lower(&table.name) == *alias) =>
            {
                Some(column.clone())
            }
            _ => None,
        });
        match projected {
            Some(name) => key.push(name),
            None if star => key.push(column.clone()),
            None => return None,
        }
    }
    Some(key)
}

fn all_columns_key(left: &Expression) -> Keys {
    let Expression::Select(select) = left else {
        return Vec::new();
    };
    let output: Vec<Projection<'_>> = projections(select);
    if output
        .iter()
        .all(|item| matches!(item, Projection::Named { .. }))
    {
        vec![output_names(&output)]
    } else {
        Vec::new()
    }
}

/// Columns a ranking window partitions and orders by, generously resolved to input aliases.
pub(crate) fn window_columns(
    partition_by: &[Expression],
    order_by: &[&Expression],
) -> Vec<(Option<String>, String)> {
    partition_by
        .iter()
        .chain(order_by.iter().copied())
        .flat_map(columns)
        .map(|column| (qualifier(column), lower(&column.name.name)))
        .collect()
}

/// Whether some input key is covered by the window's partition and order columns.
pub(crate) fn covers(keys: &[InputKey], window: &[(Option<String>, String)]) -> bool {
    keys.iter().any(|key| key_covered(key, window))
}

fn key_covered(key: &InputKey, window: &[(Option<String>, String)]) -> bool {
    key.iter()
        .all(|(alias, column)| window_has(window, alias, column))
}

fn window_has(window: &[(Option<String>, String)], alias: &str, column: &str) -> bool {
    window.iter().any(|(qualifier, name)| {
        name == column && qualifier.as_deref().is_none_or(|table| table == alias)
    })
}

/// Keys of declared relations and of each top-level CTE, in definition order.
pub(crate) fn key_environment(request: &QualityRequest<'_>) -> KeyEnvironment {
    let mut environment: KeyEnvironment = KeyEnvironment {
        declared: lowered_keys(request.relation_keys),
        ctes: HashMap::new(),
        row_numbers: HashMap::new(),
    };
    for statement in request.statements {
        let Expression::Select(select) = statement else {
            continue;
        };
        for cte in select.with.iter().flat_map(|with| with.ctes.iter()) {
            let keys = environment.query_keys(&cte.this);
            environment.ctes.insert(lower(&cte.alias.name), keys);
            if let Expression::Select(body) = &cte.this {
                environment
                    .row_numbers
                    .insert(lower(&cte.alias.name), row_number_outputs(body));
            }
        }
    }
    environment
}

fn lowered_keys(keys: &HashMap<String, Keys>) -> HashMap<String, Keys> {
    let mut lowered: HashMap<String, Keys> = HashMap::new();
    for (name, relation_keys) in keys {
        let mut converted: Keys = Vec::new();
        for key in relation_keys {
            let mut columns: Vec<String> = Vec::new();
            for column in key {
                columns.push(lower(column));
            }
            converted.push(columns);
        }
        lowered.insert(lower(name), converted);
    }
    lowered
}

/// `(output name, partition output columns)` for each `ROW_NUMBER() OVER (PARTITION BY ...)` output.
fn row_number_outputs(select: &Select) -> Vec<(String, Vec<String>)> {
    let output: Vec<Projection<'_>> = projections(select);
    let mut found: Vec<(String, Vec<String>)> = Vec::new();
    for item in &output {
        let Projection::Named {
            name,
            expression: Expression::WindowFunction(window),
        } = item
        else {
            continue;
        };
        if !matches!(window.this, Expression::RowNumber(_)) || window.over.partition_by.is_empty() {
            continue;
        }
        if let Some(key) = output_key_of(&window.over.partition_by, &output) {
            found.push((name.clone(), key));
        }
    }
    found
}

/// Columns a filter pins to the first row, as in `WHERE rn = 1 AND ...`.
fn first_row_filters(condition: &Expression) -> Vec<String> {
    let mut found: Vec<String> = Vec::new();
    let mut pending: Vec<&Expression> = vec![condition];
    while let Some(expression) = pending.pop() {
        match expression {
            Expression::And(operation) => {
                pending.push(&operation.left);
                pending.push(&operation.right);
            }
            Expression::Paren(paren) => pending.push(&paren.this),
            Expression::Eq(operation) => {
                if let (Expression::Column(column), Expression::Literal(literal))
                | (Expression::Literal(literal), Expression::Column(column)) =
                    (&operation.left, &operation.right)
                    && matches!(literal.as_ref(), Literal::Number(text) if text == FIRST_ROW)
                {
                    found.push(lower(&column.name.name));
                }
            }
            _ => {}
        }
    }
    found
}
