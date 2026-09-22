//! Experimental borrowed-tree type evaluation with immutable lexical CTE outputs.

use std::collections::{HashMap, HashSet};
use std::rc::Rc;

use polyglot_sql::expressions::{DataType, Select, Star, With};
use polyglot_sql::{Dialect, DialectType, Expression, ValidationSchema};

type Outputs = Vec<(String, Option<String>)>;
type Relations = HashMap<String, Rc<Outputs>>;
pub(super) const NULL_TYPE: &str = "\0NULL";
const SQL_WILDCARD: &str = "*";

pub(super) fn infer(
    expression: &Expression,
    schema: Option<&ValidationSchema>,
    functions: &HashMap<String, String>,
    dialect: DialectType,
) -> HashMap<String, String> {
    let mut types: HashMap<String, String> = HashMap::new();
    for (name, data_type) in infer_outputs(expression, schema, functions, dialect) {
        if let Some(value) = data_type.filter(|value| value != NULL_TYPE) {
            types.insert(name, value);
        }
    }
    types
}

pub(super) fn infer_outputs(
    expression: &Expression,
    schema: Option<&ValidationSchema>,
    functions: &HashMap<String, String>,
    dialect: DialectType,
) -> Outputs {
    let mut relations = Relations::new();
    if let Some(schema) = schema {
        for table in &schema.tables {
            relations.insert(
                table.name.to_lowercase(),
                Rc::new(
                    table
                        .columns
                        .iter()
                        .map(|column| (column.name.clone(), Some(column.data_type.clone())))
                        .collect(),
                ),
            );
        }
    }
    let context = TypeContext { functions, dialect };
    context.query(expression, &relations)
}

struct TypeContext<'a> {
    functions: &'a HashMap<String, String>,
    dialect: DialectType,
}

impl TypeContext<'_> {
    fn query(&self, expression: &Expression, inherited: &Relations) -> Outputs {
        let expression = unwrapped(expression);
        let mut relations = inherited.clone();
        if let Some(with) = query_with(expression) {
            for cte in &with.ctes {
                let mut outputs = self.query(&cte.this, &relations);
                for ((name, _), alias) in outputs.iter_mut().zip(&cte.columns) {
                    *name = alias.name.clone();
                }
                relations.insert(cte.alias.name.to_lowercase(), Rc::new(outputs));
            }
        }
        match expression {
            Expression::Select(select) => self.select(select, &relations),
            Expression::Union(set) => self.set(&set.left, &set.right, set.by_name, &relations),
            Expression::Intersect(set) => self.set(&set.left, &set.right, set.by_name, &relations),
            Expression::Except(set) => self.set(&set.left, &set.right, set.by_name, &relations),
            Expression::Subquery(subquery) => self.query(&subquery.this, &relations),
            _ => Vec::new(),
        }
    }

    fn set(
        &self,
        left: &Expression,
        right: &Expression,
        by_name: bool,
        relations: &Relations,
    ) -> Outputs {
        let left = self.query(left, relations);
        let right = self.query(right, relations);
        if by_name {
            return left
                .into_iter()
                .map(|(name, value)| {
                    let other = lookup(&right, &name).flatten();
                    let common = common_type(value.as_deref(), other);
                    (name, common)
                })
                .collect();
        }
        if left.len() != right.len() {
            return Vec::new();
        }
        left.into_iter()
            .zip(right)
            .map(|((name, left), (_, right))| {
                (name, common_type(left.as_deref(), right.as_deref()))
            })
            .collect()
    }

    fn select(&self, select: &Select, relations: &Relations) -> Outputs {
        let mut aliases = Relations::new();
        let tables = select
            .from
            .iter()
            .flat_map(|from| &from.expressions)
            .chain(select.joins.iter().map(|join| &join.this));
        for source in tables {
            if let Expression::Subquery(subquery) = unwrapped(source)
                && let Some(alias) = &subquery.alias
            {
                let mut outputs = self.query(&subquery.this, relations);
                for ((name, _), alias) in outputs.iter_mut().zip(&subquery.column_aliases) {
                    *name = alias.name.clone();
                }
                aliases.insert(alias.name.to_lowercase(), Rc::new(outputs));
            }
            if let Expression::Table(table) = unwrapped(source)
                && let Some(outputs) = relations.get(&table.name.name.to_lowercase())
            {
                aliases.insert(table.name.name.to_lowercase(), outputs.clone());
                if let Some(alias) = &table.alias {
                    aliases.insert(alias.name.to_lowercase(), outputs.clone());
                }
            }
        }
        let mut result: Outputs = Vec::new();
        for projection in &select.expressions {
            let projection = unwrapped(projection);
            if let Expression::Star(star) = projection {
                result.extend(star_outputs(star, &aliases));
            } else {
                let name = projection.get_output_name();
                if !name.is_empty() && name != SQL_WILDCARD {
                    let inner = match projection {
                        Expression::Alias(alias) => &alias.this,
                        _ => projection,
                    };
                    let value = if matches!(unwrapped(inner), Expression::Null(_)) {
                        Some(NULL_TYPE.to_string())
                    } else {
                        self.expression(inner, &aliases).or_else(|| {
                            inner
                                .inferred_type()
                                .filter(|data_type| **data_type != DataType::Unknown)
                                .and_then(|data_type| self.cast_type(data_type))
                        })
                    };
                    result.push((name.to_string(), value));
                }
            }
        }
        result
    }

    fn expression(&self, expression: &Expression, aliases: &Relations) -> Option<String> {
        let expression = unwrapped(expression);
        let function_name = match expression {
            Expression::Function(function) => function.name.as_str(),
            Expression::AggregateFunction(function) => function.name.as_str(),
            _ => expression.variant_name(),
        };
        if !matches!(expression, Expression::Column(_))
            && let Some(value) = self.functions.get(&function_name.to_uppercase())
        {
            return Some(value.clone());
        }
        match expression {
            Expression::Alias(alias) => self.expression(&alias.this, aliases),
            Expression::Cast(cast) | Expression::TryCast(cast) => self.cast_type(&cast.to),
            Expression::Column(column) => {
                if let Some(table) = &column.table {
                    return lookup(aliases.get(&table.name.to_lowercase())?, &column.name.name)
                        .flatten()
                        .map(str::to_string);
                }
                let mut seen: HashSet<*const Outputs> = HashSet::new();
                let mut values = aliases
                    .values()
                    .filter(|source| seen.insert(Rc::as_ptr(source)))
                    .filter_map(|source| lookup(source, &column.name.name).flatten());
                let value = values.next()?;
                values.next().is_none().then(|| value.to_string())
            }
            Expression::Boolean(_)
            | Expression::And(_)
            | Expression::Between(_)
            | Expression::Eq(_)
            | Expression::Exists(_)
            | Expression::Gt(_)
            | Expression::Gte(_)
            | Expression::ILike(_)
            | Expression::In(_)
            | Expression::Is(_)
            | Expression::IsNull(_)
            | Expression::Like(_)
            | Expression::Lt(_)
            | Expression::Lte(_)
            | Expression::Neq(_)
            | Expression::Not(_)
            | Expression::Or(_)
            | Expression::RegexpLike(_) => Some("BOOLEAN".to_string()),
            Expression::Min(function) | Expression::Max(function) => {
                self.expression(&function.this, aliases)
            }
            Expression::WindowFunction(function) => self.expression(&function.this, aliases),
            Expression::WithinGroup(function) => self.expression(&function.this, aliases),
            Expression::Case(case) => self.results(
                case.whens
                    .iter()
                    .map(|(_, result)| result)
                    .chain(case.else_.iter()),
                aliases,
            ),
            Expression::IfFunc(function) => self.results(
                std::iter::once(&function.true_value).chain(function.false_value.iter()),
                aliases,
            ),
            Expression::Coalesce(function) => self.results(function.expressions.iter(), aliases),
            Expression::Concat(binary) => {
                let left = self.string_operand(&binary.left, aliases)?;
                let right = self.string_operand(&binary.right, aliases)?;
                (is_text(&left) && is_text(&right)).then(|| "TEXT".to_string())
            }
            _ => None,
        }
    }

    fn string_operand(&self, expression: &Expression, aliases: &Relations) -> Option<String> {
        if matches!(unwrapped(expression), Expression::Literal(literal) if matches!(literal.as_ref(), polyglot_sql::expressions::Literal::String(_)))
        {
            Some("TEXT".to_string())
        } else {
            self.expression(expression, aliases)
        }
    }

    fn results<'a>(
        &self,
        values: impl Iterator<Item = &'a Expression>,
        aliases: &Relations,
    ) -> Option<String> {
        let mut types = values
            .filter(|value| !matches!(unwrapped(value), Expression::Null(_)))
            .map(|value| self.expression(value, aliases));
        let first = types.next()??;
        types
            .all(|value| {
                value
                    .as_deref()
                    .is_some_and(|value| canonical(value) == canonical(&first))
            })
            .then_some(first)
    }

    fn cast_type(&self, data_type: &DataType) -> Option<String> {
        match Dialect::get(self.dialect).generate(&Expression::DataType(data_type.clone())) {
            Ok(rendered) => Some(rendered.replace(", ", ",")),
            Err(_) => None,
        }
    }
}

fn query_with(expression: &Expression) -> Option<&With> {
    match expression {
        Expression::Select(query) => query.with.as_ref(),
        Expression::Union(query) => query.with.as_ref(),
        Expression::Intersect(query) => query.with.as_ref(),
        Expression::Except(query) => query.with.as_ref(),
        _ => None,
    }
}

fn unwrapped(mut expression: &Expression) -> &Expression {
    loop {
        expression = match expression {
            Expression::Annotated(annotation) => &annotation.this,
            Expression::Paren(paren) => &paren.this,
            _ => return expression,
        };
    }
}

fn lookup<'a>(outputs: &'a Outputs, name: &str) -> Option<Option<&'a str>> {
    outputs
        .iter()
        .find(|(key, _)| key == name)
        .or_else(|| {
            outputs
                .iter()
                .find(|(key, _)| key.eq_ignore_ascii_case(name))
        })
        .map(|(_, value)| value.as_deref())
}

fn star_outputs(star: &Star, aliases: &Relations) -> Outputs {
    if star
        .rename
        .as_ref()
        .is_some_and(|values| !values.is_empty())
    {
        return Vec::new();
    }
    let sources: Vec<_> = match &star.table {
        Some(table) => aliases
            .get(&table.name.to_lowercase())
            .into_iter()
            .collect(),
        None => {
            let mut seen: HashSet<*const Outputs> = HashSet::new();
            aliases
                .values()
                .filter(|source| seen.insert(Rc::as_ptr(source)))
                .collect()
        }
    };
    let excluded: HashSet<_> = star
        .except
        .iter()
        .flatten()
        .map(|name| name.name.to_lowercase())
        .chain(
            star.replace
                .iter()
                .flatten()
                .map(|alias| alias.alias.name.to_lowercase()),
        )
        .collect();
    let mut result: Outputs = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    let mut ambiguous: HashSet<String> = HashSet::new();
    for source in sources {
        for (name, value) in source.iter() {
            let key = name.to_lowercase();
            if excluded.contains(&key) || value.is_none() {
                continue;
            }
            if !seen.insert(key.clone()) {
                ambiguous.insert(key);
            } else {
                result.push((name.clone(), value.clone()));
            }
        }
    }
    result.retain(|(name, _)| !ambiguous.contains(&name.to_lowercase()));
    result
}

fn canonical(value: &str) -> String {
    let compact: String = value
        .chars()
        .filter(|c| !c.is_ascii_whitespace())
        .flat_map(char::to_uppercase)
        .collect();
    match compact.as_str() {
        "INTEGER" => "INT".to_string(),
        "VARCHAR" | "STRING" => "TEXT".to_string(),
        _ => compact,
    }
}

fn is_text(value: &str) -> bool {
    matches!(value, "TEXT" | "STRING") || value.starts_with("VARCHAR")
}

fn common_type(left: Option<&str>, right: Option<&str>) -> Option<String> {
    match (left, right) {
        (Some("\0NULL"), Some("\0NULL")) => None,
        (Some("\0NULL"), right) => right.map(str::to_string),
        (left, Some("\0NULL")) => left.map(str::to_string),
        (Some(left), Some(right)) if canonical(left) == canonical(right) => Some(left.to_string()),
        _ => None,
    }
}
