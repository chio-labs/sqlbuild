//! Stable SQLBuild boundary around Polyglot schema-aware validation.

use polyglot_sql::{
    Dialect, DialectType, Expression, ExpressionWalk, Resolver, SchemaValidationOptions,
    ValidationError, ValidationSchema, build_scope,
    mapping_schema_from_validation_schema_with_dialect, validate_with_schema,
};
use serde::Deserialize;

#[derive(Deserialize)]
struct ValidationRequest {
    sql: String,
    #[serde(default = "default_dialect")]
    dialect: String,
    schema: ValidationSchema,
    #[serde(default)]
    options: SchemaValidationOptions,
}

fn default_dialect() -> String {
    "generic".to_string()
}

pub(crate) fn validate_json(request_json: &str) -> Result<String, String> {
    let request: ValidationRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let dialect: DialectType = request.dialect.parse().map_err(|error| {
        format!(
            "unsupported Polyglot dialect '{}': {error}",
            request.dialect
        )
    })?;
    let mut result = validate_with_schema(
        request.sql.as_str(),
        dialect,
        &request.schema,
        &request.options,
    );
    if result.valid {
        let statements = Dialect::get(dialect)
            .parse(&request.sql)
            .map_err(|error| error.to_string())?;
        let schema = mapping_schema_from_validation_schema_with_dialect(&request.schema, dialect);
        for statement in statements {
            let scope = build_scope(&statement);
            collect_missing_clause_columns(&scope, &schema, &mut result.errors);
        }
        result.valid = !result
            .errors
            .iter()
            .any(|error| error.severity == polyglot_sql::ValidationSeverity::Error);
    }
    serde_json::to_string(&result).map_err(|error| error.to_string())
}

fn collect_missing_clause_columns(
    scope: &polyglot_sql::Scope,
    schema: &polyglot_sql::MappingSchema,
    errors: &mut Vec<ValidationError>,
) {
    let mut resolver = Resolver::new(scope, schema, false);
    if let Expression::Select(select) = &scope.expression {
        let projection_aliases: std::collections::HashSet<String> = select
            .expressions
            .iter()
            .filter_map(|expression| match expression {
                Expression::Alias(alias) => Some(alias.alias.to_string().to_lowercase()),
                _ => None,
            })
            .collect();
        if let Some(qualify) = &select.qualify {
            for node in qualify.this.dfs() {
                let Expression::Column(column) = node else {
                    continue;
                };
                if column.table.is_none()
                    && projection_aliases.contains(&column.name.to_string().to_lowercase())
                {
                    continue;
                }
                if !column_exists(column, scope, &mut resolver) {
                    let mut error = ValidationError::error(
                        format!("Unknown column '{}' in QUALIFY", column.name),
                        "E201",
                    );
                    if let Some(span) = column.span {
                        error = error
                            .with_location(span.line, span.column)
                            .with_span(Some(span.start), Some(span.end));
                    }
                    errors.push(error);
                }
            }
        }
        for join in &select.joins {
            for identifier in &join.using {
                let column_name = identifier.to_string();
                let matching_sources = scope
                    .sources
                    .keys()
                    .filter(|source_name| {
                        resolver
                            .get_source_columns(source_name)
                            .is_ok_and(|columns| columns.iter().any(|name| name == &column_name))
                    })
                    .count();
                if matching_sources < 2 {
                    errors.push(ValidationError::error(
                        format!("Unknown column '{column_name}' in JOIN USING"),
                        "E201",
                    ));
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
        collect_missing_clause_columns(child, schema, errors);
    }
}

fn column_exists(
    column: &polyglot_sql::expressions::Column,
    scope: &polyglot_sql::Scope,
    resolver: &mut Resolver<'_>,
) -> bool {
    let column_name = column.name.to_string();
    if let Some(table) = &column.table {
        return resolver
            .get_source_columns(&table.to_string())
            .is_ok_and(|columns| columns.iter().any(|name| name == &column_name));
    }
    scope.sources.keys().any(|source_name| {
        resolver
            .get_source_columns(source_name)
            .is_ok_and(|columns| columns.iter().any(|name| name == &column_name))
    })
}

#[cfg(test)]
mod tests {
    use super::validate_json;

    #[test]
    fn given_unknown_column_when_validating_then_returns_structured_error() {
        let response = validate_json(
            r#"{
                "sql":"SELECT missing FROM upstream",
                "dialect":"generic",
                "schema":{"strict":true,"tables":[{"name":"upstream","columns":[{"name":"id","type":"INTEGER"}]}]},
                "options":{}
            }"#,
        )
        .expect("request should be valid");

        assert!(response.contains("\"valid\":false"));
        assert!(response.contains("\"code\":\"E201\""));
        assert!(response.contains("missing"));
    }
}
