use crate::constants::ENFORCED_CONTRACT;
use crate::models::{Column, Fault, Model, RuleMetadata};
use crate::rules::_helpers::evaluation::{plain_select, root_select, sole_table_name, top_ctes};
use crate::rules::models::FaultCollector;
use sqlparser::ast::{Expr, Query, Select, SelectItem, SetExpr, SetQuantifier, Spanned};

#[derive(Clone, Copy)]
struct OutputScope<'a> {
    columns: &'a [Column],
    set_branch: bool,
    by_name: bool,
}

struct OutputRule<'a> {
    model: &'a Model,
    rule: &'a RuleMetadata,
    faults: &'a FaultCollector,
}

pub(crate) fn evaluate(query: &Query, model: &Model, rule: &RuleMetadata, faults: &FaultCollector) {
    if model
        .config
        .get("contract")
        .and_then(serde_json::Value::as_str)
        != Some(ENFORCED_CONTRACT)
        || !model
            .columns
            .iter()
            .any(|column| !column.data_type.is_empty())
    {
        return;
    }
    let evaluator = OutputRule {
        model,
        rule,
        faults,
    };
    if let Some((boundary, columns)) = final_cte_output_boundary(query, &model.columns) {
        evaluator.evaluate_set(
            &boundary.body,
            OutputScope {
                columns: &columns,
                set_branch: false,
                by_name: false,
            },
        );
        return;
    }
    let columns = columns_in_output_order(&query.body, &model.columns);
    evaluator.evaluate_set(
        &query.body,
        OutputScope {
            columns: &columns,
            set_branch: false,
            by_name: false,
        },
    );
}

impl OutputRule<'_> {
    fn evaluate_set(&self, set_expr: &SetExpr, scope: OutputScope<'_>) {
        match set_expr {
            SetExpr::Select(select) => self.evaluate_select(select, scope),
            SetExpr::Query(query) => self.evaluate_set(&query.body, scope),
            SetExpr::SetOperation {
                set_quantifier,
                left,
                right,
                ..
            } => {
                let operation_by_name = set_quantifier_by_name(set_quantifier);
                let branch_scope = OutputScope {
                    columns: scope.columns,
                    set_branch: true,
                    by_name: operation_by_name,
                };
                self.evaluate_set(left, branch_scope);
                self.evaluate_set(right, branch_scope);
            }
            _ => self.push(
                None,
                format!(
                    "model {:?} does not expose an explicit SELECT output boundary",
                    self.model.name
                ),
                "Project the enforced contract columns explicitly and establish every declared type at that boundary."
                    .into(),
            ),
        }
    }

    fn evaluate_select(&self, select: &Select, scope: OutputScope<'_>) {
        for (index, item) in select.projection.iter().enumerate() {
            if matches!(
                item,
                SelectItem::Wildcard(_) | SelectItem::QualifiedWildcard(_, _)
            ) {
                self.push(
                    Some(source_position(item)),
                    "wildcard output does not establish enforced contract types explicitly".into(),
                    "Enumerate the contract columns; pass through columns with proven exact types and cast every calculated output."
                        .into(),
                );
                continue;
            }
            self.evaluate_projection(index, item, scope);
        }
    }

    fn evaluate_projection(&self, index: usize, item: &SelectItem, scope: OutputScope<'_>) {
        let output_name = projection_output_name(item);
        let column = if scope.by_name {
            output_name
                .as_deref()
                .and_then(|name| column_named(scope.columns, name))
        } else {
            scope.columns.get(index)
        };
        let Some(column) = column.filter(|column| !column.data_type.is_empty()) else {
            return;
        };
        let Some(expr) = projection_expression(item) else {
            return;
        };
        let direct = direct_column_name(expr).is_some();
        let cast_type = explicit_cast_type(expr);
        let explicit_cast = cast_type.is_some();
        let cast_matches_contract = cast_type
            .as_ref()
            .is_some_and(|data_type| type_spelling_equal(data_type, &column.data_type));
        let passes = cast_matches_contract || column.type_proven && direct && !scope.set_branch;
        if passes {
            return;
        }
        let name = output_name.unwrap_or_else(|| column.name.clone());
        let reason = if explicit_cast && !cast_matches_contract {
            "has an outer cast that does not target its declared contract type"
        } else if direct && scope.set_branch {
            "is in a set-operation branch that must cast each output explicitly"
        } else if direct {
            "is a passthrough whose type is not proven against the declared contract"
        } else {
            "is calculated without an outer explicit cast"
        };
        self.push(
            Some(source_position(expr)),
            format!(
                "output {:?} {reason}; declared type is {}",
                name, column.data_type
            ),
            format!(
                "Wrap the complete expression in CAST(... AS {}) or establish that exact type on a direct upstream column.",
                column.data_type
            ),
        );
    }

    fn push(&self, position: Option<(u64, u64)>, message: String, remediation: String) {
        let (line, column) = position.unwrap_or((1, 1));
        self.faults.push(Fault {
            code: self.rule.code.clone(),
            path: self.model.relative_path.clone(),
            line,
            column,
            message,
            remediation,
        });
    }
}

fn final_cte_output_boundary<'a>(
    query: &'a Query,
    columns: &[Column],
) -> Option<(&'a Query, Vec<Column>)> {
    let final_cte = top_ctes(query).last()?;
    let final_name = &final_cte.alias.name.value;
    let terminal_reads_final_cte = sole_table_name(query)
        .is_some_and(|name| name.eq_ignore_ascii_case(final_name))
        && root_select(query).is_some_and(|select| plain_select(select, true))
        && query.order_by.is_none()
        && query.limit_clause.is_none()
        && query.fetch.is_none()
        && query.locks.is_empty();
    if !terminal_reads_final_cte {
        return None;
    }
    let select = root_select(query)?;
    let cte_column_aliases: Vec<String> = final_cte
        .alias
        .columns
        .iter()
        .map(|column| column.name.value.clone())
        .collect();
    if select.projection.len() == 1
        && matches!(
            select.projection[0],
            SelectItem::Wildcard(_) | SelectItem::QualifiedWildcard(_, _)
        )
    {
        return Some((
            &final_cte.query,
            columns_in_output_order_with_missing(
                &final_cte.query.body,
                columns,
                &cte_column_aliases,
            ),
        ));
    }
    if select.projection.len() != columns.len() {
        return None;
    }
    let mut boundary_columns: Vec<Column> = Vec::with_capacity(columns.len());
    for item in &select.projection {
        let output_name = projection_output_name(item)?;
        let column = column_named(columns, &output_name)?;
        let source_name = projection_expression(item).and_then(direct_column_name)?;
        let mut boundary_column = column.clone();
        boundary_column.name = source_name;
        boundary_columns.push(boundary_column);
    }
    let ordered_columns = columns_in_output_order_with_missing(
        &final_cte.query.body,
        &boundary_columns,
        &cte_column_aliases,
    );
    Some((&final_cte.query, ordered_columns))
}

fn columns_in_output_order_with_missing(
    set_expr: &SetExpr,
    columns: &[Column],
    cte_column_aliases: &[String],
) -> Vec<Column> {
    let Some(output_names) = set_expression_output_names_with_missing(set_expr) else {
        return columns.to_vec();
    };
    output_names
        .into_iter()
        .enumerate()
        .map(|(index, body_name)| {
            let exposed_name = cte_column_aliases
                .get(index)
                .map(String::as_str)
                .or(body_name.as_deref());
            let mut column = exposed_name
                .and_then(|name| column_named(columns, name))
                .cloned()
                .unwrap_or_default();
            if let Some(body_name) = body_name {
                column.name = body_name;
            }
            column
        })
        .collect()
}

fn columns_in_output_order(set_expr: &SetExpr, columns: &[Column]) -> Vec<Column> {
    let Some(output_names) = set_expression_output_names(set_expr) else {
        return columns.to_vec();
    };
    let mut ordered: Vec<Column> = Vec::with_capacity(output_names.len());
    for name in output_names {
        let Some(column) = column_named(columns, &name) else {
            return columns.to_vec();
        };
        ordered.push(column.clone());
    }
    ordered
}

fn column_named<'a>(columns: &'a [Column], name: &str) -> Option<&'a Column> {
    columns
        .iter()
        .find(|column| column.name.eq_ignore_ascii_case(name))
}

fn set_expression_output_names(set_expr: &SetExpr) -> Option<Vec<String>> {
    match set_expr {
        SetExpr::Select(select) => {
            let mut names: Vec<String> = Vec::with_capacity(select.projection.len());
            for item in &select.projection {
                names.push(projection_output_name(item)?);
            }
            Some(names)
        }
        SetExpr::Query(query) => set_expression_output_names(&query.body),
        SetExpr::SetOperation { left, .. } => set_expression_output_names(left),
        _ => None,
    }
}

fn set_expression_output_names_with_missing(set_expr: &SetExpr) -> Option<Vec<Option<String>>> {
    match set_expr {
        SetExpr::Select(select) => Some(
            select
                .projection
                .iter()
                .map(projection_output_name)
                .collect(),
        ),
        SetExpr::Query(query) => set_expression_output_names_with_missing(&query.body),
        SetExpr::SetOperation {
            left,
            right,
            set_quantifier,
            ..
        } => {
            let mut names = set_expression_output_names_with_missing(left)?;
            if set_quantifier_by_name(set_quantifier) {
                for right_name in set_expression_output_names_with_missing(right)? {
                    let already_present = right_name.as_ref().is_some_and(|right_name| {
                        names
                            .iter()
                            .flatten()
                            .any(|left_name| left_name.eq_ignore_ascii_case(right_name))
                    });
                    if !already_present {
                        names.push(right_name);
                    }
                }
            }
            Some(names)
        }
        _ => None,
    }
}

fn set_quantifier_by_name(set_quantifier: &SetQuantifier) -> bool {
    matches!(
        set_quantifier,
        SetQuantifier::ByName | SetQuantifier::AllByName | SetQuantifier::DistinctByName
    )
}

fn projection_output_name(item: &SelectItem) -> Option<String> {
    match item {
        SelectItem::ExprWithAlias { alias, .. } => Some(alias.value.clone()),
        SelectItem::UnnamedExpr(Expr::Identifier(identifier)) => Some(identifier.value.clone()),
        SelectItem::UnnamedExpr(Expr::CompoundIdentifier(identifiers)) => identifiers
            .last()
            .map(|identifier| identifier.value.clone()),
        _ => None,
    }
}

fn projection_expression(item: &SelectItem) -> Option<&Expr> {
    match item {
        SelectItem::UnnamedExpr(expr) | SelectItem::ExprWithAlias { expr, .. } => Some(expr),
        _ => None,
    }
}

fn direct_column_name(expr: &Expr) -> Option<String> {
    match unwrap_nested_expression(expr) {
        Expr::Identifier(identifier) => Some(identifier.value.clone()),
        Expr::CompoundIdentifier(identifiers) => identifiers
            .last()
            .map(|identifier| identifier.value.clone()),
        _ => None,
    }
}

fn explicit_cast_type(expr: &Expr) -> Option<String> {
    let Expr::Cast { data_type, .. } = unwrap_nested_expression(expr) else {
        return None;
    };
    Some(data_type.to_string())
}

fn type_spelling_equal(left: &str, right: &str) -> bool {
    let normalize = |value: &str| {
        value
            .chars()
            .filter(|character| !character.is_whitespace())
            .flat_map(char::to_uppercase)
            .collect::<String>()
    };
    normalize(left) == normalize(right)
}

fn unwrap_nested_expression(mut expr: &Expr) -> &Expr {
    while let Expr::Nested(inner) = expr {
        expr = inner;
    }
    expr
}

fn source_position<T: Spanned>(node: &T) -> (u64, u64) {
    let start = node.span().start;
    (start.line, start.column)
}
