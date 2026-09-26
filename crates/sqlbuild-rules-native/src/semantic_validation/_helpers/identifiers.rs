//! Fold only binding identifiers in the AST, retaining SQL and authored spans.

use polyglot_sql::expressions::{Identifier, With};
use polyglot_sql::tokens::Span;
use polyglot_sql::{Expression, ExpressionWalk};
use std::cell::RefCell;

pub(super) type AuthoredNames = Vec<(String, String, Option<Span>)>;

fn fold(identifier: &mut Identifier, authored: &RefCell<AuthoredNames>) {
    if !identifier.quoted {
        return;
    }
    let original = identifier.name.clone();
    identifier.name.make_ascii_uppercase();
    authored
        .borrow_mut()
        .push((identifier.name.clone(), original, identifier.span));
}

fn fold_with(with: &mut With, authored: &RefCell<AuthoredNames>) {
    for cte in &mut with.ctes {
        fold(&mut cte.alias, authored);
        for identifier in &mut cte.columns {
            fold(identifier, authored);
        }
    }
}

pub(super) fn fold_statements(
    statements: Vec<Expression>,
) -> Result<(Vec<Expression>, AuthoredNames), String> {
    let authored = RefCell::new(Vec::new());
    let mut output = Vec::with_capacity(statements.len());
    for statement in statements {
        output.push(
            statement
                .transform_owned(|mut expression| {
                    match &mut expression {
                        Expression::Identifier(identifier) => fold(identifier, &authored),
                        Expression::Column(column) => {
                            fold(&mut column.name, &authored);
                            if let Some(table) = &mut column.table {
                                fold(table, &authored);
                            }
                        }
                        Expression::Alias(alias) => fold(&mut alias.alias, &authored),
                        Expression::Table(table) => {
                            fold(&mut table.name, &authored);
                            for identifier in
                                [&mut table.schema, &mut table.catalog, &mut table.alias]
                                    .into_iter()
                                    .flatten()
                            {
                                fold(identifier, &authored);
                            }
                            for identifier in &mut table.column_aliases {
                                fold(identifier, &authored);
                            }
                        }
                        Expression::Subquery(query) => {
                            if let Some(alias) = &mut query.alias {
                                fold(alias, &authored);
                            }
                            for identifier in &mut query.column_aliases {
                                fold(identifier, &authored);
                            }
                        }
                        Expression::Values(values) => {
                            if let Some(alias) = &mut values.alias {
                                fold(alias, &authored);
                            }
                            for identifier in &mut values.column_aliases {
                                fold(identifier, &authored);
                            }
                        }
                        Expression::Select(select) => {
                            if let Some(with) = &mut select.with {
                                fold_with(with, &authored);
                            }
                            for join in &mut select.joins {
                                for identifier in &mut join.using {
                                    fold(identifier, &authored);
                                }
                            }
                            if let Some(windows) = &mut select.windows {
                                for window in windows {
                                    fold(&mut window.name, &authored);
                                }
                            }
                        }
                        Expression::With(with) => fold_with(with, &authored),
                        Expression::Union(query) => {
                            if let Some(with) = &mut query.with {
                                fold_with(with, &authored);
                            }
                        }
                        Expression::Intersect(query) => {
                            if let Some(with) = &mut query.with {
                                fold_with(with, &authored);
                            }
                        }
                        Expression::Except(query) => {
                            if let Some(with) = &mut query.with {
                                fold_with(with, &authored);
                            }
                        }
                        Expression::Join(join) => {
                            for identifier in &mut join.using {
                                fold(identifier, &authored);
                            }
                        }
                        Expression::Star(star) => {
                            if let Some(table) = &mut star.table {
                                fold(table, &authored);
                            }
                            if let Some(columns) = &mut star.except {
                                for column in columns {
                                    fold(column, &authored);
                                }
                            }
                            if let Some(columns) = &mut star.rename {
                                for (old, new) in columns {
                                    fold(old, &authored);
                                    fold(new, &authored);
                                }
                            }
                        }
                        Expression::Pivot(pivot) => {
                            if let Some(alias) = &mut pivot.alias {
                                fold(alias, &authored);
                            }
                            for column in &mut pivot.alias_columns {
                                fold(column, &authored);
                            }
                            if let Some(with) = &mut pivot.with {
                                fold_with(with, &authored);
                            }
                        }
                        Expression::Unpivot(pivot) => {
                            fold(&mut pivot.value_column, &authored);
                            fold(&mut pivot.name_column, &authored);
                            if let Some(alias) = &mut pivot.alias {
                                fold(alias, &authored);
                            }
                            for column in pivot
                                .alias_columns
                                .iter_mut()
                                .chain(&mut pivot.extra_value_columns)
                            {
                                fold(column, &authored);
                            }
                        }
                        Expression::Unnest(unnest) => {
                            if let Some(alias) = &mut unnest.alias {
                                fold(alias, &authored);
                            }
                            if let Some(alias) = &mut unnest.offset_alias {
                                fold(alias, &authored);
                            }
                        }
                        Expression::Lateral(lateral) => {
                            if lateral.alias_quoted
                                && let Some(alias) = &mut lateral.alias
                            {
                                let original = alias.clone();
                                alias.make_ascii_uppercase();
                                authored.borrow_mut().push((alias.clone(), original, None));
                            }
                            for alias in &mut lateral.column_aliases {
                                alias.make_ascii_uppercase();
                            }
                        }
                        Expression::Cte(cte) => {
                            fold(&mut cte.alias, &authored);
                            for identifier in &mut cte.columns {
                                fold(identifier, &authored);
                            }
                        }
                        _ => {}
                    }
                    Ok(Some(expression))
                })
                .map_err(|error| error.to_string())?,
        );
    }
    Ok((output, authored.into_inner()))
}
