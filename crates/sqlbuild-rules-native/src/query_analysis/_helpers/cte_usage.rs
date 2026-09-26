use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use polyglot_sql::expressions::Column;
use polyglot_sql::optimizer::normalize_identifiers::normalize_identifiers;
use polyglot_sql::optimizer::qualify_columns::{QualifyColumnsOptions, qualify_columns};
use polyglot_sql::resolver::Resolver;
use polyglot_sql::schema::MappingSchema;
use polyglot_sql::scope::{Scope, SourceInfo, SourceKind, build_scope, walk_in_scope};
use polyglot_sql::{DialectType, Expression, ExpressionWalk, ValidationSchema};

use crate::constants::{CTE_ROOT_SCOPE, CTE_USAGE_MAX_FUNCTION_DEPTH, SQL_WILDCARD};
use crate::query_analysis::engine::StringInterner;
use crate::query_analysis::models::{CompactCteUsage, CteOutputSlot, CteSlotUsage, CteUsageBatch};

#[derive(Debug)]
struct UsageGraph<'a> {
    schema: &'a MappingSchema,
    ctes: Vec<CteSlotUsage>,
    identities: HashMap<usize, usize>,
}

#[derive(Debug)]
struct ScopeBindings {
    scope: Scope,
    targets: HashMap<String, usize>,
    ordinals: HashMap<String, HashMap<String, Option<usize>>>,
}

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
    let withs: Vec<&polyglot_sql::expressions::With> = expression
        .dfs()
        .filter_map(|node| match node {
            Expression::Select(select) => select.with.as_ref(),
            Expression::Union(set) => set.with.as_ref(),
            Expression::Intersect(set) => set.with.as_ref(),
            Expression::Except(set) => set.with.as_ref(),
            _ => None,
        })
        .collect();
    if withs.is_empty() {
        return Ok(Vec::new());
    }
    if withs.iter().any(|with| with.recursive) {
        return Err(
            "Recursive CTE output-slot binding is not supported; remove recursion".to_owned(),
        );
    }
    let empty = ValidationSchema {
        tables: Vec::new(),
        strict: Some(false),
    };
    let schema = polyglot_sql::validation::mapping_schema_from_validation_schema_with_dialect(
        schema.unwrap_or(&empty),
        dialect,
    );
    let normalized = normalize_identifiers(expression.clone(), Some(dialect));
    let original = build_scope(&normalized);
    let normalized = complete_alias_lists(normalized)?;
    let qualified = qualify_columns(
        normalized,
        &schema,
        &QualifyColumnsOptions {
            expand_alias_refs: true,
            expand_stars: true,
            infer_schema: Some(true),
            allow_partial_qualification: true,
            dialect: Some(dialect),
        },
    )
    .map_err(|error| format!("CTE slot binding could not be proven: {error}"))?;
    let scope = build_scope(&qualified);
    let mut graph = UsageGraph {
        schema: &schema,
        ctes: Vec::new(),
        identities: HashMap::new(),
    };
    graph.register(&scope, &original, CTE_ROOT_SCOPE)?;
    graph.visit(&scope, &[])?;
    Ok(graph.ctes)
}

impl UsageGraph<'_> {
    fn register(&mut self, scope: &Scope, original: &Scope, path: &str) -> Result<(), String> {
        if scope.cte_scopes.len() != original.cte_scopes.len() {
            return Err("Qualification changed the CTE scope structure".to_owned());
        }
        let exported = final_source(&original.expression);
        for (ordinal, (child, raw)) in scope
            .cte_scopes
            .iter()
            .zip(&original.cte_scopes)
            .enumerate()
        {
            let Expression::Cte(cte) = &child.expression else {
                continue;
            };
            let Expression::Cte(raw_cte) = &raw.expression else {
                continue;
            };
            let source = scope
                .cte_sources
                .get(&cte.alias.name)
                .ok_or("Missing CTE binding")?;
            let mut output_scope = Scope::new(Expression::Null(polyglot_sql::expressions::Null));
            output_scope.cte_sources = scope.cte_sources.clone();
            output_scope
                .sources
                .insert(cte.alias.name.clone(), source.clone());
            let mut resolver = Resolver::new(&output_scope, self.schema, true);
            let names = resolver
                .get_source_columns(&cte.alias.name)
                .map_err(|error| error.to_string())?;
            if names.is_empty() || names.iter().any(|name| name == SQL_WILDCARD) {
                return Err(format!(
                    "Cannot enumerate output slots for CTE {} without its input schema",
                    cte.alias.name
                ));
            }
            if matches!(query(&raw_cte.this), Expression::Select(select) if select.expressions.len() > names.len())
            {
                return Err(
                    "The CTE column alias list does not expose every output slot".to_owned(),
                );
            }
            if !cte.columns.is_empty()
                && matches!(query(&cte.this), Expression::Select(select)
                if select.expressions.len() != names.len() || select.expressions.iter().any(|item| super::borrowed_facts::projection_star(item).is_some()))
            {
                return Err(
                    "Cannot prove the complete CTE alias list across a star; enumerate its columns"
                        .to_owned(),
                );
            }
            let set_operation = matches!(
                query(&cte.this),
                Expression::Union(_) | Expression::Intersect(_) | Expression::Except(_)
            );
            let distinct = matches!(query(&cte.this), Expression::Select(select) if select.distinct || select.distinct_on.is_some());
            let index = self.ctes.len();
            self.identities
                .insert(Arc::as_ptr(&source.expression) as usize, index);
            let child_path = format!("{path}.ctes[{ordinal}]");
            self.ctes.push(CteSlotUsage {
                scope: child_path.clone(),
                name: cte.alias.name.clone(),
                original: raw_cte.as_ref().clone(),
                slots: names
                    .into_iter()
                    .map(|name| CteOutputSlot {
                        name,
                        read: false,
                        semantically_required: set_operation,
                    })
                    .collect(),
                distinct,
                set_operation,
                model_output: path == CTE_ROOT_SCOPE
                    && exported.as_deref() == Some(&cte.alias.name),
            });
            self.register(child, raw, &child_path)?;
        }
        for (label, children, originals) in [
            (
                "subqueries",
                &scope.subquery_scopes,
                &original.subquery_scopes,
            ),
            (
                "derived",
                &scope.derived_table_scopes,
                &original.derived_table_scopes,
            ),
            ("lateral", &scope.udtf_scopes, &original.udtf_scopes),
            ("branches", &scope.union_scopes, &original.union_scopes),
        ] {
            if children.len() != originals.len() {
                return Err("Qualification changed nested query scopes".to_owned());
            }
            for (index, (child, raw)) in children.iter().zip(originals).enumerate() {
                self.register(child, raw, &format!("{path}.{label}[{index}]"))?;
            }
        }
        Ok(())
    }

    fn visit(&mut self, scope: &Scope, parents: &[&ScopeBindings]) -> Result<(), String> {
        let selected = self.selected_scope(scope)?;
        let mut visible = vec![&selected];
        visible.extend_from_slice(parents);
        let output_names: HashSet<String> = match query(&scope.expression) {
            Expression::Select(select) => select.expressions.iter().filter_map(|item| {
                let Expression::Alias(alias) = item else { return None; };
                (!matches!(&alias.this, Expression::Column(column) if column.table.is_none() && column.name.name == alias.alias.name)).then(|| alias.alias.name.clone())
            }).collect(),
            _ => HashSet::new(),
        };
        for expression in walk_in_scope(query(&scope.expression), false) {
            if let Expression::Column(column) = expression {
                if column.table.is_none() && output_names.contains(&column.name.name) {
                    continue;
                }
                self.read(
                    column,
                    &visible,
                    scope.scope_type == polyglot_sql::scope::ScopeType::SetOperation,
                )?;
            }
        }
        for child in &scope.cte_scopes {
            self.visit(child, parents)?;
        }
        for child in scope.subquery_scopes.iter().chain(&scope.udtf_scopes) {
            self.visit(child, &visible)?;
        }
        for child in scope.derived_table_scopes.iter().chain(&scope.union_scopes) {
            self.visit(child, parents)?;
        }
        Ok(())
    }

    fn read(
        &mut self,
        column: &Column,
        visible: &[&ScopeBindings],
        required: bool,
    ) -> Result<(), String> {
        for binding in visible {
            let table = if let Some(table) = &column.table {
                if !binding.scope.sources.contains_key(&table.name) {
                    continue;
                }
                table.name.clone()
            } else {
                let mut resolver = Resolver::new(&binding.scope, self.schema, true);
                if resolver.is_ambiguous(&column.name.name) {
                    return Err(format!(
                        "Column {} has ambiguous slot bindings",
                        column.name.name
                    ));
                }
                let Some(table) = resolver.get_table(&column.name.name) else {
                    continue;
                };
                table
            };
            let Some(&cte_index) = binding.targets.get(&table) else {
                return Ok(());
            };
            let slots = &mut self.ctes[cte_index].slots;
            let ordinal = binding
                .ordinals
                .get(&table)
                .and_then(|columns| columns.get(&column.name.name))
                .copied()
                .flatten()
                .ok_or_else(|| {
                    format!(
                        "Column {table}.{} does not identify one CTE output slot",
                        column.name.name
                    )
                })?;
            let slot = slots
                .get_mut(ordinal)
                .ok_or("Alias ordinal exceeds CTE output slots")?;
            slot.read = true;
            slot.semantically_required |= required;
            return Ok(());
        }
        Err(format!(
            "Column {} has no visible relation binding",
            column.name.name
        ))
    }

    fn selected_scope(&self, scope: &Scope) -> Result<ScopeBindings, String> {
        let mut selected = Scope::new(Expression::Null(polyglot_sql::expressions::Null));
        let mut targets: HashMap<String, usize> = HashMap::new();
        selected.cte_sources = scope.cte_sources.clone();
        selected.sources = scope
            .sources
            .iter()
            .filter(|(_, source)| source.kind != SourceKind::Cte)
            .map(|(name, source)| (name.clone(), source.clone()))
            .collect();
        for node in walk_in_scope(query(&scope.expression), false) {
            if let Expression::Table(table) = node {
                let alias = table.alias.as_ref().unwrap_or(&table.name).name.clone();
                let mut source = if table.schema.is_none() && table.catalog.is_none() {
                    scope.cte_sources.get(&table.name.name).cloned()
                } else {
                    None
                };
                if let Some(source) = &mut source
                    && let Some(&index) = self
                        .identities
                        .get(&(Arc::as_ptr(&source.expression) as usize))
                {
                    targets.insert(alias.clone(), index);
                    if !table.column_aliases.is_empty() {
                        if table.column_aliases.len() > self.ctes[index].slots.len() {
                            return Err("Alias column list exceeds CTE output slots".to_owned());
                        }
                        let Expression::Cte(cte) = source.expression.as_ref() else {
                            return Err("Missing CTE source".to_owned());
                        };
                        let mut cte = cte.as_ref().clone();
                        cte.columns = table.column_aliases.clone();
                        cte.columns.extend(
                            self.ctes[index]
                                .slots
                                .iter()
                                .skip(cte.columns.len())
                                .map(|slot| {
                                    polyglot_sql::expressions::Identifier::new(slot.name.clone())
                                }),
                        );
                        source.expression = Arc::new(Expression::Cte(Box::new(cte)));
                    }
                }
                selected.sources.insert(
                    alias,
                    source
                        .unwrap_or_else(|| SourceInfo::new(node.clone(), false, SourceKind::Table)),
                );
            }
        }
        let mut ordinals: HashMap<String, HashMap<String, Option<usize>>> = HashMap::new();
        let mut resolver = Resolver::new(&selected, self.schema, true);
        for alias in targets.keys() {
            let mut columns: HashMap<String, Option<usize>> = HashMap::new();
            for (ordinal, name) in resolver
                .get_source_columns(alias)
                .map_err(|error| error.to_string())?
                .into_iter()
                .enumerate()
            {
                let value = (!columns.contains_key(&name)).then_some(ordinal);
                columns.insert(name, value);
            }
            ordinals.insert(alias.clone(), columns);
        }
        Ok(ScopeBindings {
            scope: selected,
            targets,
            ordinals,
        })
    }
}

fn complete_alias_lists(expression: Expression) -> Result<Expression, String> {
    expression
        .transform_owned(|mut node| {
            let with = match &mut node {
                Expression::Select(select) => select.with.as_mut(),
                Expression::Union(set) => set.with.as_mut(),
                Expression::Intersect(set) => set.with.as_mut(),
                Expression::Except(set) => set.with.as_mut(),
                _ => None,
            };
            for cte in with.into_iter().flat_map(|with| &mut with.ctes) {
                if !cte.columns.is_empty()
                    && let Expression::Select(select) = query(&cte.this)
                {
                    let names: Option<Vec<polyglot_sql::expressions::Identifier>> = select
                        .expressions
                        .iter()
                        .map(|projection| match projection {
                            Expression::Alias(alias) => Some(alias.alias.clone()),
                            Expression::Column(column) => Some(column.name.clone()),
                            _ => None,
                        })
                        .collect();
                    if let Some(names) = names {
                        cte.columns
                            .extend(names.into_iter().skip(cte.columns.len()));
                    }
                }
            }
            Ok(Some(node))
        })
        .map_err(|error| error.to_string())
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
            Expression::Subquery(subquery) => &subquery.this,
            Expression::Paren(paren) => &paren.this,
            Expression::Annotated(annotated) => &annotated.this,
            _ => return expression,
        };
    }
}

fn compact(ctes: Vec<CteSlotUsage>) -> CompactCteUsage {
    let mut result = CompactCteUsage {
        version: 1,
        strings: Vec::new(),
        ctes: Vec::new(),
        slots: Vec::new(),
    };
    let mut interner = StringInterner::default();
    for (cte_index, cte) in ctes.into_iter().enumerate() {
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
