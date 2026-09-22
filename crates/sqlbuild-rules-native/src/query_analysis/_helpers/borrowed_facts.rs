//! Experimental immutable CTE output graph over one borrowed syntax tree.

use std::collections::{BTreeSet, HashMap};
use std::rc::Rc;

use polyglot_sql::expressions::{Column, JoinKind, Select, Star, With};
use polyglot_sql::{
    DialectType, Expression, ProjectionNullability, TransformKind, ValidationSchema,
};
const SQL_WILDCARD: &str = "*";

#[derive(Clone, Debug)]
pub(super) struct OutputFact {
    pub name: String,
    pub upstream: Rc<BTreeSet<(String, String)>>,
    pub nullability: ProjectionNullability,
    pub resolved: bool,
    pub transform: TransformKind,
}

#[derive(Clone)]
struct Source {
    outputs: Rc<Vec<OutputFact>>,
    columns: Rc<HashMap<String, Option<usize>>>,
    physical: Option<String>,
    null_extended: bool,
}

impl Source {
    fn new(outputs: Vec<OutputFact>, physical: Option<String>) -> Self {
        let mut columns: HashMap<String, Option<usize>> = HashMap::new();
        for (index, output) in outputs.iter().enumerate() {
            let key = output.name.to_lowercase();
            let value = (!columns.contains_key(&key)).then_some(index);
            columns.insert(key, value);
        }
        Self {
            outputs: Rc::new(outputs),
            columns: Rc::new(columns),
            physical,
            null_extended: false,
        }
    }
}

type Relations = HashMap<String, Source>;
type Sources = Vec<(String, Source)>;
type Aliases = HashMap<String, Option<OutputFact>>;

pub(super) fn infer(
    expression: &Expression,
    schema: Option<&ValidationSchema>,
    dialect: DialectType,
) -> Vec<OutputFact> {
    let mut relations = Relations::new();
    if let Some(schema) = schema {
        for table in &schema.tables {
            let outputs: Vec<OutputFact> = table
                .columns
                .iter()
                .map(|column| OutputFact {
                    name: column.name.clone(),
                    upstream: Rc::new(BTreeSet::from([(table.name.clone(), column.name.clone())])),
                    nullability: match column.nullable {
                        Some(false) => ProjectionNullability::NonNull,
                        Some(true) => ProjectionNullability::Nullable,
                        None => ProjectionNullability::Unknown,
                    },
                    resolved: true,
                    transform: TransformKind::Direct,
                })
                .collect();
            relations.insert(
                table.name.to_lowercase(),
                Source::new(outputs, Some(table.name.clone())),
            );
        }
    }
    query(
        expression,
        &relations,
        matches!(
            dialect,
            DialectType::Snowflake
                | DialectType::DuckDB
                | DialectType::Redshift
                | DialectType::Spark
                | DialectType::Databricks
        ),
    )
}

fn query(expression: &Expression, inherited: &Relations, lateral_aliases: bool) -> Vec<OutputFact> {
    let expression = unwrapped(expression);
    let mut relations = inherited.clone();
    if let Some(with) = query_with(expression) {
        for cte in &with.ctes {
            let mut outputs = query(&cte.this, &relations, lateral_aliases);
            for (output, alias) in outputs.iter_mut().zip(&cte.columns) {
                output.name = alias.name.clone();
            }
            relations.insert(cte.alias.name.to_lowercase(), Source::new(outputs, None));
        }
    }
    match expression {
        Expression::Select(select) => select_outputs(select, &relations, lateral_aliases),
        Expression::Union(set) => set_outputs(
            query(&set.left, &relations, lateral_aliases),
            query(&set.right, &relations, lateral_aliases),
            set.by_name,
        ),
        Expression::Intersect(set) => set_outputs(
            query(&set.left, &relations, lateral_aliases),
            query(&set.right, &relations, lateral_aliases),
            set.by_name,
        ),
        Expression::Except(set) => set_outputs(
            query(&set.left, &relations, lateral_aliases),
            query(&set.right, &relations, lateral_aliases),
            set.by_name,
        ),
        Expression::Subquery(subquery) => query(&subquery.this, &relations, lateral_aliases),
        _ => Vec::new(),
    }
}

fn set_outputs(
    mut left: Vec<OutputFact>,
    right: Vec<OutputFact>,
    by_name: bool,
) -> Vec<OutputFact> {
    for (index, output) in left.iter_mut().enumerate() {
        let other = if by_name {
            right
                .iter()
                .find(|other| other.name.eq_ignore_ascii_case(&output.name))
        } else {
            right.get(index)
        };
        if let Some(other) = other {
            if !Rc::ptr_eq(&output.upstream, &other.upstream) {
                Rc::make_mut(&mut output.upstream).extend(other.upstream.iter().cloned());
            }
            output.resolved &= other.resolved;
            output.nullability = merge_nullability(output.nullability, other.nullability);
        } else {
            output.nullability = ProjectionNullability::Nullable;
        }
    }
    if by_name {
        for mut output in right {
            if !left
                .iter()
                .any(|other| other.name.eq_ignore_ascii_case(&output.name))
            {
                output.nullability = ProjectionNullability::Nullable;
                left.push(output);
            }
        }
    }
    left
}

fn select_outputs(
    select: &Select,
    relations: &Relations,
    lateral_aliases: bool,
) -> Vec<OutputFact> {
    let mut sources: Sources = Vec::new();
    for expression in select.from.iter().flat_map(|from| &from.expressions) {
        if let Some(source) = source(expression, relations, &sources, lateral_aliases) {
            sources.push(source);
        }
    }
    for join in &select.joins {
        if matches!(join.kind, JoinKind::Right | JoinKind::Full) {
            for (_, source) in &mut sources {
                source.null_extended = true;
            }
        }
        if let Some((name, mut source)) = source(&join.this, relations, &sources, lateral_aliases) {
            source.null_extended = matches!(join.kind, JoinKind::Left | JoinKind::Full);
            sources.push((name, source));
        }
    }
    let mut outputs: Vec<OutputFact> = Vec::new();
    let mut aliases = Aliases::new();
    for projection in &select.expressions {
        let projection = unwrapped(projection);
        if let Expression::Star(star) = projection {
            outputs.extend(star_outputs(star, &sources));
            continue;
        }
        let name = projection.get_output_name();
        if name.is_empty() || name == SQL_WILDCARD {
            continue;
        }
        let expression = match projection {
            Expression::Alias(alias) => &alias.this,
            _ => projection,
        };
        let mut fact = expression_fact(expression, &sources, &aliases);
        fact.name = name.to_string();
        if let Expression::Column(column) = unwrapped(expression)
            && select
                .where_clause
                .as_ref()
                .is_some_and(|clause| filtered_non_null(&clause.this, column))
        {
            fact.nullability = ProjectionNullability::NonNull;
        }
        if lateral_aliases && matches!(projection, Expression::Alias(_)) {
            let key = name.to_lowercase();
            let value = (!aliases.contains_key(&key)).then(|| fact.clone());
            aliases.insert(key, value);
        }
        outputs.push(fact);
    }
    outputs
}

fn source(
    expression: &Expression,
    relations: &Relations,
    preceding: &Sources,
    lateral_aliases: bool,
) -> Option<(String, Source)> {
    match unwrapped(expression) {
        Expression::Table(table) => {
            let name = table.alias.as_ref().unwrap_or(&table.name).name.clone();
            let source = relations
                .get(&table.name.name.to_lowercase())
                .cloned()
                .unwrap_or_else(|| Source::new(Vec::new(), Some(table.name.name.clone())));
            Some((name, source))
        }
        Expression::Subquery(subquery) => Some((
            subquery.alias.as_ref()?.name.clone(),
            Source::new(query(&subquery.this, relations, lateral_aliases), None),
        )),
        Expression::Lateral(lateral) if matches!(unwrapped(&lateral.this), Expression::Function(function) if function.name.eq_ignore_ascii_case("FLATTEN")) =>
        {
            let fact = expression_fact(&lateral.this, preceding, &Aliases::new());
            let names: Vec<String> = if lateral.column_aliases.is_empty() {
                ["SEQ", "KEY", "PATH", "INDEX", "VALUE", "THIS"]
                    .into_iter()
                    .map(str::to_string)
                    .collect()
            } else {
                lateral.column_aliases.clone()
            };
            Some((
                lateral.alias.clone()?,
                Source::new(
                    names
                        .into_iter()
                        .map(|name| OutputFact {
                            name,
                            nullability: ProjectionNullability::Unknown,
                            ..fact.clone()
                        })
                        .collect(),
                    None,
                ),
            ))
        }
        _ => None,
    }
}

fn column_fact(column: &Column, sources: &Sources, aliases: &Aliases) -> Option<OutputFact> {
    let mut matched = None;
    let column_key = column.name.name.to_lowercase();
    for (name, source) in sources {
        if column
            .table
            .as_ref()
            .is_some_and(|table| !table.name.eq_ignore_ascii_case(name))
        {
            continue;
        }
        let candidate = match source.columns.get(&column_key) {
            Some(Some(index)) => source.outputs.get(*index),
            Some(None) => return None,
            None => None,
        };
        let mut candidate = match (candidate, &source.physical) {
            (Some(output), _) => output.clone(),
            (None, Some(physical)) if source.outputs.is_empty() => OutputFact {
                name: column.name.name.clone(),
                upstream: Rc::new(BTreeSet::from([(
                    physical.clone(),
                    column.name.name.clone(),
                )])),
                nullability: ProjectionNullability::Unknown,
                resolved: false,
                transform: TransformKind::Direct,
            },
            _ => continue,
        };
        if source.null_extended {
            candidate.nullability = ProjectionNullability::Nullable;
        }
        if matched.is_some() {
            return None;
        }
        matched = Some(candidate);
    }
    matched.or_else(|| {
        (column.table.is_none() && sources.iter().all(|(_, source)| !source.outputs.is_empty()))
            .then(|| {
                aliases
                    .get(&column.name.name.to_lowercase())
                    .cloned()
                    .flatten()
            })
            .flatten()
    })
}

fn expression_fact(expression: &Expression, sources: &Sources, aliases: &Aliases) -> OutputFact {
    let expression = unwrapped(expression);
    if let Expression::Column(column) = expression
        && let Some(mut fact) = column_fact(column, sources, aliases)
    {
        fact.transform = TransformKind::Direct;
        return fact;
    }
    if let Expression::Cast(cast) | Expression::TryCast(cast) | Expression::SafeCast(cast) =
        expression
    {
        let mut fact = expression_fact(&cast.this, sources, aliases);
        fact.transform = TransformKind::Cast;
        fact.nullability = nullability(expression, sources, aliases);
        return fact;
    }
    let mut upstream: BTreeSet<(String, String)> = BTreeSet::new();
    let mut resolved = true;
    for node in polyglot_sql::scope::walk_in_scope(expression, false) {
        if let Expression::Column(column) = node {
            if column.name.name == SQL_WILDCARD {
                continue;
            }
            if let Some(fact) = column_fact(column, sources, aliases) {
                upstream.extend(fact.upstream.iter().cloned());
                resolved &= fact.resolved;
            } else {
                resolved = false;
            }
        }
    }
    let transform = match expression {
        Expression::Column(_) | Expression::Identifier(_) => TransformKind::Direct,
        Expression::Cast(_) | Expression::TryCast(_) | Expression::SafeCast(_) => {
            TransformKind::Cast
        }
        Expression::Literal(_) | Expression::Boolean(_) | Expression::Null(_) => {
            TransformKind::Constant
        }
        _ if polyglot_sql::traversal::contains_aggregate(expression) => TransformKind::Aggregation,
        _ => TransformKind::Expression,
    };
    OutputFact {
        name: String::new(),
        upstream: Rc::new(upstream),
        nullability: nullability(expression, sources, aliases),
        resolved,
        transform,
    }
}

fn nullability(
    expression: &Expression,
    sources: &Sources,
    aliases: &Aliases,
) -> ProjectionNullability {
    match unwrapped(expression) {
        Expression::Column(column) => column_fact(column, sources, aliases)
            .map_or(ProjectionNullability::Unknown, |fact| fact.nullability),
        Expression::Null(_) => ProjectionNullability::Nullable,
        Expression::Literal(_)
        | Expression::Boolean(_)
        | Expression::Count(_)
        | Expression::IsNull(_) => ProjectionNullability::NonNull,
        Expression::Cast(cast) => nullability(&cast.this, sources, aliases),
        Expression::Coalesce(function) => {
            let values: Vec<_> = function
                .expressions
                .iter()
                .map(|value| nullability(value, sources, aliases))
                .collect();
            if values.contains(&ProjectionNullability::NonNull) {
                ProjectionNullability::NonNull
            } else if !values.is_empty()
                && values
                    .iter()
                    .all(|value| *value == ProjectionNullability::Nullable)
            {
                ProjectionNullability::Nullable
            } else {
                ProjectionNullability::Unknown
            }
        }
        _ => ProjectionNullability::Unknown,
    }
}

fn star_outputs(star: &Star, sources: &Sources) -> Vec<OutputFact> {
    let mut outputs: Vec<OutputFact> = Vec::new();
    for (name, source) in sources {
        if star
            .table
            .as_ref()
            .is_some_and(|table| !table.name.eq_ignore_ascii_case(name))
        {
            continue;
        }
        for output in source.outputs.iter() {
            if star
                .except
                .iter()
                .flatten()
                .any(|name| name.name.eq_ignore_ascii_case(&output.name))
            {
                continue;
            }
            let mut output = output.clone();
            if source.null_extended {
                output.nullability = ProjectionNullability::Nullable;
            }
            if let Some((_, alias)) = star
                .rename
                .iter()
                .flatten()
                .find(|(name, _)| name.name.eq_ignore_ascii_case(&output.name))
            {
                output.name = alias.name.clone();
            }
            if let Some(alias) = star
                .replace
                .iter()
                .flatten()
                .find(|alias| alias.alias.name.eq_ignore_ascii_case(&output.name))
            {
                let name = output.name.clone();
                output = expression_fact(&alias.this, sources, &Aliases::new());
                output.name = name;
            }
            outputs.push(output);
        }
    }
    outputs
}

fn filtered_non_null(expression: &Expression, column: &Column) -> bool {
    match unwrapped(expression) {
        Expression::And(binary) => {
            filtered_non_null(&binary.left, column) || filtered_non_null(&binary.right, column)
        }
        Expression::IsNull(predicate) if predicate.not => {
            matches!(unwrapped(&predicate.this), Expression::Column(filtered)
            if filtered.name.name.eq_ignore_ascii_case(&column.name.name) && filtered.table.as_ref().map(|table| table.name.to_lowercase()) == column.table.as_ref().map(|table| table.name.to_lowercase()))
        }
        _ => false,
    }
}

fn merge_nullability(
    left: ProjectionNullability,
    right: ProjectionNullability,
) -> ProjectionNullability {
    if left == ProjectionNullability::Nullable || right == ProjectionNullability::Nullable {
        ProjectionNullability::Nullable
    } else if left == ProjectionNullability::NonNull && right == ProjectionNullability::NonNull {
        ProjectionNullability::NonNull
    } else {
        ProjectionNullability::Unknown
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

fn query_with(expression: &Expression) -> Option<&With> {
    match expression {
        Expression::Select(query) => query.with.as_ref(),
        Expression::Union(query) => query.with.as_ref(),
        Expression::Intersect(query) => query.with.as_ref(),
        Expression::Except(query) => query.with.as_ref(),
        _ => None,
    }
}
