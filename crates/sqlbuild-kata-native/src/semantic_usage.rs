//! On-demand direct non-projection column usage extraction.

use polyglot_sql::{
    Dialect, DialectType, Expression, ExpressionWalk, Resolver, SchemaValidationOptions,
    ValidationSchema, build_scope, mapping_schema_from_validation_schema_with_dialect,
    validate_with_schema,
};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

#[derive(Deserialize)]
struct UsageRequest {
    sql: String,
    #[serde(default = "default_dialect")]
    dialect: String,
    schema: ValidationSchema,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct UsageResponse {
    uses: Vec<UsageFact>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct UsageFact {
    context: String,
    expression_sql: String,
    source_name: String,
    source_alias: Option<String>,
    column: String,
    confidence: String,
    start: Option<usize>,
    end: Option<usize>,
    line: Option<usize>,
    column_offset: Option<usize>,
}

fn default_dialect() -> String {
    "generic".to_string()
}

pub(crate) fn analyze_json(request_json: &str) -> Result<String, String> {
    let request: UsageRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let dialect: DialectType = request.dialect.parse().map_err(|error| {
        format!(
            "unsupported Polyglot dialect '{}': {error}",
            request.dialect
        )
    })?;
    let validation = validate_with_schema(
        &request.sql,
        dialect,
        &request.schema,
        &SchemaValidationOptions {
            check_references: true,
            strict: Some(true),
            ..SchemaValidationOptions::default()
        },
    );
    if !validation.valid {
        return serde_json::to_string(&UsageResponse { uses: Vec::new() })
            .map_err(|error| error.to_string());
    }
    let statements = Dialect::get(dialect)
        .parse(&request.sql)
        .map_err(|error| error.to_string())?;
    let schema = mapping_schema_from_validation_schema_with_dialect(&request.schema, dialect);
    let mut uses = Vec::new();
    for statement in statements {
        let scope = build_scope(&statement);
        collect_scope(&scope, &schema, &mut uses);
    }
    dedupe(&mut uses);
    serde_json::to_string(&UsageResponse { uses }).map_err(|error| error.to_string())
}

fn collect_scope(
    scope: &polyglot_sql::Scope,
    schema: &polyglot_sql::MappingSchema,
    uses: &mut Vec<UsageFact>,
) {
    let mut resolver = Resolver::new(scope, schema, false);
    if let Expression::Select(select) = &scope.expression {
        for join in &select.joins {
            if let Some(expression) = &join.on {
                collect_expression(expression, "join_on", scope, &mut resolver, uses);
            }
            if let Some(expression) = &join.match_condition {
                collect_expression(
                    expression,
                    "join_match_condition",
                    scope,
                    &mut resolver,
                    uses,
                );
            }
            for identifier in &join.using {
                collect_using(identifier.to_string(), scope, &mut resolver, uses);
            }
        }
        if let Some(clause) = &select.where_clause {
            collect_expression(&clause.this, "where", scope, &mut resolver, uses);
        }
        if let Some(clause) = &select.group_by {
            for expression in &clause.expressions {
                collect_expression(expression, "group_by", scope, &mut resolver, uses);
            }
        }
        if let Some(clause) = &select.having {
            collect_expression(&clause.this, "having", scope, &mut resolver, uses);
        }
        if let Some(clause) = &select.qualify {
            collect_expression(&clause.this, "qualify", scope, &mut resolver, uses);
        }
        if let Some(clause) = &select.order_by {
            for ordered in &clause.expressions {
                collect_expression(&ordered.this, "order_by", scope, &mut resolver, uses);
            }
        }
        for projection in &select.expressions {
            for node in projection.dfs() {
                if let Expression::WindowFunction(window) = node {
                    for expression in &window.over.partition_by {
                        collect_expression(
                            expression,
                            "window_partition_by",
                            scope,
                            &mut resolver,
                            uses,
                        );
                    }
                    for ordered in &window.over.order_by {
                        collect_expression(
                            &ordered.this,
                            "window_order_by",
                            scope,
                            &mut resolver,
                            uses,
                        );
                    }
                }
            }
        }
    }
    for child in scope
        .cte_scopes
        .iter()
        .chain(scope.subquery_scopes.iter())
        .chain(scope.derived_table_scopes.iter())
        .chain(scope.udtf_scopes.iter())
        .chain(scope.union_scopes.iter())
    {
        collect_scope(child, schema, uses);
    }
}

fn collect_expression(
    expression: &Expression,
    context: &str,
    scope: &polyglot_sql::Scope,
    resolver: &mut Resolver<'_>,
    uses: &mut Vec<UsageFact>,
) {
    let expression_sql = expression.to_string();
    for node in expression.dfs() {
        let Expression::Column(column) = node else {
            continue;
        };
        let column_name = column.name.to_string();
        let alias = column
            .table
            .as_ref()
            .map(ToString::to_string)
            .or_else(|| resolver.get_table(&column_name));
        let Some(source_alias) = alias else {
            continue;
        };
        let Some(source) = scope.sources.get(&source_alias) else {
            continue;
        };
        let source_name = physical_source_name(&source.expression).unwrap_or(source_alias.clone());
        let span = column.span;
        uses.push(UsageFact {
            context: context.to_string(),
            expression_sql: expression_sql.clone(),
            source_name,
            source_alias: source.alias.clone().or(Some(source_alias)),
            column: column_name,
            confidence: "high".to_string(),
            start: span.map(|value| value.start),
            end: span.map(|value| value.end),
            line: span.map(|value| value.line),
            column_offset: span.map(|value| value.column),
        });
    }
}

fn collect_using(
    column_name: String,
    scope: &polyglot_sql::Scope,
    resolver: &mut Resolver<'_>,
    uses: &mut Vec<UsageFact>,
) {
    let source_names: Vec<String> = scope.sources.keys().cloned().collect();
    for source_alias in source_names {
        let Ok(columns) = resolver.get_source_columns(&source_alias) else {
            continue;
        };
        if !columns.iter().any(|column| column == &column_name) {
            continue;
        }
        let Some(source) = scope.sources.get(&source_alias) else {
            continue;
        };
        uses.push(UsageFact {
            context: "join_using".to_string(),
            expression_sql: column_name.clone(),
            source_name: physical_source_name(&source.expression).unwrap_or(source_alias.clone()),
            source_alias: source.alias.clone().or(Some(source_alias)),
            column: column_name.clone(),
            confidence: "high".to_string(),
            start: None,
            end: None,
            line: None,
            column_offset: None,
        });
    }
}

fn physical_source_name(expression: &Expression) -> Option<String> {
    match expression {
        Expression::Table(table) => Some(table.name.to_string()),
        _ => None,
    }
}

fn dedupe(uses: &mut Vec<UsageFact>) {
    let mut seen = HashSet::new();
    uses.retain(|fact| {
        seen.insert((
            fact.context.clone(),
            fact.expression_sql.clone(),
            fact.source_name.clone(),
            fact.column.clone(),
            fact.start,
        ))
    });
}

#[cfg(test)]
mod tests {
    use super::analyze_json;

    #[test]
    fn given_filter_and_join_when_analyzing_then_returns_direct_contextual_uses() {
        let response = analyze_json(
            r#"{
              "sql":"SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.active",
              "dialect":"generic",
              "schema":{"strict":true,"tables":[
                {"name":"orders","columns":[{"name":"id","type":"INTEGER"},{"name":"customer_id","type":"INTEGER"},{"name":"active","type":"BOOLEAN"}]},
                {"name":"customers","columns":[{"name":"id","type":"INTEGER"}]}
              ]}
            }"#,
        )
        .expect("usage analysis should succeed");

        assert!(response.contains("\"context\":\"join_on\""));
        assert!(response.contains("\"context\":\"where\""));
        assert!(response.contains("\"column\":\"customer_id\""));
        assert!(response.contains("\"column\":\"active\""));
    }
}
