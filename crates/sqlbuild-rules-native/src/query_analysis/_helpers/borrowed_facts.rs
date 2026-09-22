//! Immutable CTE output graph over one borrowed syntax tree.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::rc::Rc;

use polyglot_sql::expressions::{Column, Join, JoinKind, Select, Star, Values, With};
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
#[derive(Default)]
struct Sources {
    items: Vec<(String, Source)>,
    using_columns: HashMap<String, OutputFact>,
}
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
        Expression::Values(values) => values_outputs(values),
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
    let mut sources = Sources::default();
    for expression in select.from.iter().flat_map(|from| &from.expressions) {
        if let Some(source) = source(expression, relations, &sources, lateral_aliases) {
            sources.items.push(source);
        }
    }
    for join in &select.joins {
        sources = joined_sources(sources, join, relations, lateral_aliases);
    }
    let mut outputs: Vec<OutputFact> = Vec::new();
    let mut aliases = Aliases::new();
    for projection in &select.expressions {
        let projection = unwrapped(projection);
        if let Some(star) = projection_star(projection) {
            outputs.extend(star_outputs(&star, &sources));
            continue;
        }
        let name = projection.get_output_name();
        if name == SQL_WILDCARD {
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
            let mut source = relations
                .get(&table.name.name.to_lowercase())
                .cloned()
                .unwrap_or_else(|| Source::new(Vec::new(), Some(table.name.name.clone())));
            if !table.column_aliases.is_empty() {
                let mut outputs = source.outputs.as_ref().clone();
                for (output, alias) in outputs.iter_mut().zip(&table.column_aliases) {
                    output.name = alias.name.clone();
                }
                source = Source::new(outputs, source.physical);
            }
            Some((name, source))
        }
        Expression::Subquery(subquery) => {
            let mut outputs = query(&subquery.this, relations, lateral_aliases);
            for (output, alias) in outputs.iter_mut().zip(&subquery.column_aliases) {
                output.name = alias.name.clone();
            }
            Some((
                subquery.alias.as_ref()?.name.clone(),
                Source::new(outputs, None),
            ))
        }
        Expression::Values(values) => Some((
            values
                .alias
                .as_ref()
                .map_or(String::new(), |alias| alias.name.clone()),
            Source::new(values_outputs(values), None),
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

fn values_outputs(values: &Values) -> Vec<OutputFact> {
    let mut outputs: Vec<OutputFact> = Vec::new();
    for row in &values.expressions {
        let mut facts: Vec<OutputFact> = Vec::new();
        for (index, expression) in row.expressions.iter().enumerate() {
            let mut fact = expression_fact(expression, &Sources::default(), &Aliases::new());
            fact.name = values.column_aliases.get(index).map_or_else(
                || format!("column{}", index + 1),
                |alias| alias.name.clone(),
            );
            facts.push(fact);
        }
        outputs = if outputs.is_empty() {
            facts
        } else {
            set_outputs(outputs, facts, false)
        };
    }
    outputs
}

fn joined_sources(
    mut sources: Sources,
    join: &Join,
    relations: &Relations,
    lateral_aliases: bool,
) -> Sources {
    let Some((name, mut right)) = source(&join.this, relations, &sources, lateral_aliases) else {
        return sources;
    };
    let right_scope = Sources {
        items: vec![(name.clone(), right.clone())],
        ..Default::default()
    };
    let mut joined: HashMap<String, OutputFact> = HashMap::new();
    for identifier in &join.using {
        let column = Column {
            name: identifier.clone(),
            table: None,
            join_mark: false,
            trailing_comments: Vec::new(),
            span: None,
            inferred_type: None,
        };
        let left = column_fact(&column, &sources, &Aliases::new());
        let right = column_fact(&column, &right_scope, &Aliases::new());
        let output = match (left, right) {
            (Some(mut left), Some(right)) if join.kind == JoinKind::Full => {
                Rc::make_mut(&mut left.upstream).extend(right.upstream.iter().cloned());
                left.nullability = merge_nullability(left.nullability, right.nullability);
                left.resolved &= right.resolved;
                Some(left)
            }
            (_, right) if matches!(join.kind, JoinKind::Right | JoinKind::AsOfRight) => right,
            (left, _) => left,
        };
        if let Some(output) = output {
            joined.insert(identifier.name.to_lowercase(), output);
        }
    }
    if matches!(
        join.kind,
        JoinKind::Right | JoinKind::Full | JoinKind::AsOfRight
    ) {
        for (_, source) in &mut sources.items {
            source.null_extended = true;
        }
        for output in sources.using_columns.values_mut() {
            output.nullability = ProjectionNullability::Nullable;
        }
    }
    right.null_extended = matches!(
        join.kind,
        JoinKind::Left | JoinKind::Full | JoinKind::AsOfLeft | JoinKind::LeftLateral
    );
    sources.items.push((name, right));
    sources.using_columns.extend(joined);
    sources
}

fn column_fact(column: &Column, sources: &Sources, aliases: &Aliases) -> Option<OutputFact> {
    let mut matched = None;
    let column_key = column.name.name.to_lowercase();
    if column.table.is_none()
        && let Some(output) = sources.using_columns.get(&column_key)
    {
        return Some(output.clone());
    }
    for (name, source) in &sources.items {
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
        (column.table.is_none()
            && sources
                .items
                .iter()
                .all(|(_, source)| !source.outputs.is_empty()))
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
        if let Some(star) = projection_star(node) {
            let outputs = star_outputs(&star, sources);
            resolved &= !outputs.is_empty();
            for fact in outputs {
                upstream.extend(fact.upstream.iter().cloned());
                resolved &= fact.resolved;
            }
            continue;
        }
        if let Expression::Column(column) = node {
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
        Expression::Lower(function) | Expression::Upper(function) => {
            nullability(&function.this, sources, aliases)
        }
        Expression::IfFunc(function) => {
            let left = nullability(&function.true_value, sources, aliases);
            let right = function
                .false_value
                .as_ref()
                .map_or(ProjectionNullability::Nullable, |value| {
                    nullability(value, sources, aliases)
                });
            merge_nullability(left, right)
        }
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
    let mut merged: HashSet<String> = HashSet::new();
    for (name, source) in &sources.items {
        if star
            .table
            .as_ref()
            .is_some_and(|table| !table.name.eq_ignore_ascii_case(name))
        {
            continue;
        }
        if source.outputs.is_empty() {
            outputs.push(OutputFact {
                name: SQL_WILDCARD.to_string(),
                upstream: Rc::new(BTreeSet::new()),
                nullability: ProjectionNullability::Unknown,
                resolved: false,
                transform: TransformKind::Star,
            });
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
            let key = output.name.to_lowercase();
            let using_output = star
                .table
                .is_none()
                .then(|| sources.using_columns.get(&key))
                .flatten();
            if using_output.is_some() && !merged.insert(key) {
                continue;
            }
            let mut output = using_output.unwrap_or(output).clone();
            if source.null_extended && using_output.is_none() {
                output.nullability = ProjectionNullability::Nullable;
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
            if let Some((_, alias)) = star
                .rename
                .iter()
                .flatten()
                .find(|(name, _)| name.name.eq_ignore_ascii_case(&output.name))
            {
                output.name = alias.name.clone();
            }
            outputs.push(output);
        }
    }
    outputs
}

pub(super) fn projection_star(expression: &Expression) -> Option<Star> {
    match unwrapped(expression) {
        Expression::Star(star) => Some(star.clone()),
        Expression::Column(column) if column.name.name == SQL_WILDCARD => Some(Star {
            table: column.table.clone(),
            except: None,
            replace: None,
            rename: None,
            trailing_comments: Vec::new(),
            span: column.span,
        }),
        _ => None,
    }
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
