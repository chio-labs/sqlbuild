//! Fold only binding identifiers in the AST, retaining SQL and authored spans.

use polyglot_sql::expressions::{Cte, Identifier};
use polyglot_sql::optimizer::normalize_identifiers::{
    get_normalization_strategy, normalize_identifier,
};
use polyglot_sql::tokens::Span;
use polyglot_sql::{DialectType, Expression, ExpressionWalk};
use regex::{Captures, Regex};
use std::cell::RefCell;
use std::collections::HashMap;
use std::sync::LazyLock;

pub(super) type AuthoredNames = Vec<(String, String, Option<Span>)>;
const MIN_QUOTED_NAME_BYTES: usize = 2;
static ENCODED_BINDING_NAME: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| Regex::new(r"(?i)\b__SQB_ID_[0-9A-F]+\b").map_err(|error| error.to_string()));

pub(super) fn restore_names(
    message: &str,
    authored: &AuthoredNames,
    start: Option<usize>,
    end: Option<usize>,
) -> Result<String, String> {
    let mut names: HashMap<String, &str> = HashMap::new();
    for (normalized, spelling, span) in authored {
        if start.is_some_and(|start| {
            span.is_some_and(|span| start <= span.end && end.unwrap_or(start) >= span.start)
        }) {
            names.insert(normalized.to_ascii_uppercase(), spelling);
        } else {
            names
                .entry(normalized.to_ascii_uppercase())
                .or_insert(spelling);
        }
    }
    Ok(ENCODED_BINDING_NAME
        .as_ref()
        .map_err(Clone::clone)?
        .replace_all(message, |captures: &Captures<'_>| {
            names
                .get(&captures[0].to_ascii_uppercase())
                .copied()
                .unwrap_or(&captures[0])
                .to_owned()
        })
        .into_owned())
}

struct IdentifierBindings {
    names: RefCell<AuthoredNames>,
    exact_dialect: Option<DialectType>,
}

impl IdentifierBindings {
    fn borrow_mut(&self) -> std::cell::RefMut<'_, AuthoredNames> {
        self.names.borrow_mut()
    }
    fn into_inner(self) -> AuthoredNames {
        self.names.into_inner()
    }
}

pub(super) fn encoded_name(name: &str, dialect: DialectType) -> String {
    let identifier =
        if name.len() >= MIN_QUOTED_NAME_BYTES && name.starts_with('"') && name.ends_with('"') {
            Identifier::quoted(name[1..name.len() - 1].replace("\"\"", "\""))
        } else {
            Identifier::new(name)
        };
    encode_identifier(identifier, dialect)
}

fn encode_identifier(identifier: Identifier, dialect: DialectType) -> String {
    let identity = normalize_identifier(identifier, get_normalization_strategy(Some(dialect))).name;
    let mut encoded = String::from("__SQB_ID_");
    for byte in identity.as_bytes() {
        encoded.push_str(&format!("{byte:02X}"));
    }
    encoded
}

fn fold(mut identifier: Identifier, authored: &IdentifierBindings) -> Identifier {
    if !identifier.quoted && authored.exact_dialect.is_none() {
        return identifier;
    }
    let original = identifier.name.clone();
    if let Some(dialect) = authored.exact_dialect {
        identifier.name = encode_identifier(identifier.clone(), dialect);
        identifier.quoted = false;
    } else {
        identifier.name.make_ascii_uppercase();
    }
    authored
        .borrow_mut()
        .push((identifier.name.clone(), original, identifier.span));
    identifier
}

fn fold_ctes(mut ctes: Vec<Cte>, authored: &IdentifierBindings) -> Vec<Cte> {
    for cte in &mut ctes {
        cte.alias = fold(cte.alias.clone(), authored);
        for identifier in &mut cte.columns {
            *identifier = fold(identifier.clone(), authored);
        }
    }
    ctes
}

pub(super) fn fold_statements(
    statements: Vec<Expression>,
) -> Result<(Vec<Expression>, AuthoredNames), String> {
    transform_statements(statements, None)
}

pub(super) fn transform_statements(
    statements: Vec<Expression>,
    exact_dialect: Option<DialectType>,
) -> Result<(Vec<Expression>, AuthoredNames), String> {
    let authored = IdentifierBindings {
        names: RefCell::new(Vec::new()),
        exact_dialect,
    };
    let mut output = Vec::with_capacity(statements.len());
    for statement in statements {
        output.push(
            statement
                .transform_owned(|mut expression| {
                    match &mut expression {
                        Expression::Identifier(identifier) => {
                            *identifier = fold(identifier.clone(), &authored);
                        }
                        Expression::Column(column) => {
                            column.name = fold(column.name.clone(), &authored);
                            if let Some(table) = &mut column.table {
                                *table = fold(table.clone(), &authored);
                            }
                        }
                        Expression::Alias(alias) => {
                            alias.alias = fold(alias.alias.clone(), &authored);
                        }
                        Expression::Table(table) => {
                            table.name = fold(table.name.clone(), &authored);
                            for identifier in
                                [&mut table.schema, &mut table.catalog, &mut table.alias]
                                    .into_iter()
                                    .flatten()
                            {
                                *identifier = fold(identifier.clone(), &authored);
                            }
                            for identifier in &mut table.column_aliases {
                                *identifier = fold(identifier.clone(), &authored);
                            }
                        }
                        Expression::Subquery(query) => {
                            if let Some(alias) = &mut query.alias {
                                *alias = fold(alias.clone(), &authored);
                            }
                            for identifier in &mut query.column_aliases {
                                *identifier = fold(identifier.clone(), &authored);
                            }
                        }
                        Expression::Values(values) => {
                            if let Some(alias) = &mut values.alias {
                                *alias = fold(alias.clone(), &authored);
                            }
                            for identifier in &mut values.column_aliases {
                                *identifier = fold(identifier.clone(), &authored);
                            }
                        }
                        Expression::Select(select) => {
                            if let Some(with) = &mut select.with {
                                with.ctes = fold_ctes(std::mem::take(&mut with.ctes), &authored);
                            }
                            for join in &mut select.joins {
                                for identifier in &mut join.using {
                                    *identifier = fold(identifier.clone(), &authored);
                                }
                            }
                            if let Some(windows) = &mut select.windows {
                                for window in windows {
                                    window.name = fold(window.name.clone(), &authored);
                                }
                            }
                        }
                        Expression::With(with) => {
                            with.ctes = fold_ctes(std::mem::take(&mut with.ctes), &authored);
                        }
                        Expression::Union(query) => {
                            if let Some(with) = &mut query.with {
                                with.ctes = fold_ctes(std::mem::take(&mut with.ctes), &authored);
                            }
                        }
                        Expression::Intersect(query) => {
                            if let Some(with) = &mut query.with {
                                with.ctes = fold_ctes(std::mem::take(&mut with.ctes), &authored);
                            }
                        }
                        Expression::Except(query) => {
                            if let Some(with) = &mut query.with {
                                with.ctes = fold_ctes(std::mem::take(&mut with.ctes), &authored);
                            }
                        }
                        Expression::Join(join) => {
                            for identifier in &mut join.using {
                                *identifier = fold(identifier.clone(), &authored);
                            }
                        }
                        Expression::Star(star) => {
                            if let Some(table) = &mut star.table {
                                *table = fold(table.clone(), &authored);
                            }
                            if let Some(columns) = &mut star.except {
                                for column in columns {
                                    *column = fold(column.clone(), &authored);
                                }
                            }
                            if let Some(columns) = &mut star.rename {
                                for (old, new) in columns {
                                    *old = fold(old.clone(), &authored);
                                    *new = fold(new.clone(), &authored);
                                }
                            }
                        }
                        Expression::Pivot(pivot) => {
                            if let Some(alias) = &mut pivot.alias {
                                *alias = fold(alias.clone(), &authored);
                            }
                            for column in &mut pivot.alias_columns {
                                *column = fold(column.clone(), &authored);
                            }
                            if let Some(with) = &mut pivot.with {
                                with.ctes = fold_ctes(std::mem::take(&mut with.ctes), &authored);
                            }
                        }
                        Expression::Unpivot(pivot) => {
                            pivot.value_column = fold(pivot.value_column.clone(), &authored);
                            pivot.name_column = fold(pivot.name_column.clone(), &authored);
                            if let Some(alias) = &mut pivot.alias {
                                *alias = fold(alias.clone(), &authored);
                            }
                            for column in pivot
                                .alias_columns
                                .iter_mut()
                                .chain(&mut pivot.extra_value_columns)
                            {
                                *column = fold(column.clone(), &authored);
                            }
                        }
                        Expression::Unnest(unnest) => {
                            if let Some(alias) = &mut unnest.alias {
                                *alias = fold(alias.clone(), &authored);
                            }
                            if let Some(alias) = &mut unnest.offset_alias {
                                *alias = fold(alias.clone(), &authored);
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
                            cte.alias = fold(cte.alias.clone(), &authored);
                            for identifier in &mut cte.columns {
                                *identifier = fold(identifier.clone(), &authored);
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
