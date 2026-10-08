//! Python's `_build_polyglot_fast_model_column_lineage`: the parse fallback without compact facts.

use std::collections::{HashMap, HashSet};

use polyglot_sql::{ComplexityGuardOptions, Dialect, DialectType, Expression, ParseOptions};

use crate::lineage::_helpers::projections::{
    UnreadableExpression, classify_transform, is_star, projection_output_name,
    projection_upstream_columns, set_expression_selects, table_alias_map, unaliased,
};
use crate::lineage::_helpers::references::{PhysicalResource, normalized_sql, physical_resources};
use crate::lineage::_helpers::stars::star_lineage;
use crate::lineage::constants::{KIND_SELECT, KIND_UNION, MAX_FUNCTION_CALL_DEPTH};
use crate::lineage::models::{
    FastLineageOutcome, LineageColumn, LineageConfidence, LineageDeferral, LineageResourceType,
    LineageSource, LineageTransformKind,
};

/// The parse options SQLBuild's Polyglot proxy gives `parse_one`, decoded as the wheel does.
pub(crate) fn proxy_parse_options() -> Result<ParseOptions, serde_json::Error> {
    let guard: ComplexityGuardOptions = serde_json::from_value(serde_json::json!({
        "maxFunctionCallDepth": MAX_FUNCTION_CALL_DEPTH,
    }))?;
    Ok(ParseOptions {
        complexity_guard: Some(guard),
    })
}

/// Python's `parse_one(dialect=dialect or "generic")` dialect, if this parser build carries it.
pub(crate) fn lineage_dialect(name: Option<&str>) -> Option<DialectType> {
    let name = name.filter(|name| !name.is_empty()).unwrap_or("generic");
    let Ok(dialect) = name.parse::<DialectType>() else {
        return None;
    };
    matches!(
        dialect,
        DialectType::Generic
            | DialectType::PostgreSQL
            | DialectType::BigQuery
            | DialectType::Snowflake
            | DialectType::DuckDB
            | DialectType::TSQL
            | DialectType::Databricks
    )
    .then_some(dialect)
}

pub(crate) struct ParsedModel<'a> {
    pub(crate) query_sql: &'a str,
    pub(crate) inferred_names: &'a [String],
    pub(crate) schema: &'a HashMap<String, Vec<String>>,
    pub(crate) dialect: Option<DialectType>,
    pub(crate) options: &'a Result<ParseOptions, serde_json::Error>,
}

pub(crate) fn parsed_model_lineage(model: &ParsedModel<'_>) -> FastLineageOutcome {
    let Some(dialect) = model.dialect else {
        return FastLineageOutcome::Deferred(LineageDeferral::UnsupportedDialect);
    };
    let Ok(options) = model.options else {
        return FastLineageOutcome::Deferred(LineageDeferral::NativeFailure);
    };
    let physical = physical_resources(model.query_sql);
    let sql = normalized_sql(model.query_sql);
    let mut statements = match Dialect::get(dialect).parse_with_options(&sql, options) {
        Ok(statements) => statements,
        Err(error) => return FastLineageOutcome::Unparsed(error.to_string()),
    };
    if statements.len() != 1 {
        return FastLineageOutcome::Unparsed(format!(
            "Expected 1 statement, found {}",
            statements.len()
        ));
    }
    let parsed = statements.remove(0);
    let built = match parsed.variant_name() {
        KIND_UNION => union_lineage(&parsed, model, &physical),
        KIND_SELECT => select_lineage(&parsed, model, &physical),
        _ => Ok(None),
    };
    match built {
        Ok(Some((columns, has_star))) => FastLineageOutcome::Built { columns, has_star },
        Ok(None) => FastLineageOutcome::Omitted,
        Err(UnreadableExpression) => FastLineageOutcome::Deferred(LineageDeferral::NativeFailure),
    }
}

type BuiltLineage = Option<(Vec<LineageColumn>, bool)>;

fn select_lineage(
    parsed: &Expression,
    model: &ParsedModel<'_>,
    physical: &[PhysicalResource],
) -> Result<BuiltLineage, UnreadableExpression> {
    let alias_map = table_alias_map(parsed, physical);
    let unqualified = alias_map.single_resource();
    let mut lineages: Vec<LineageColumn> = Vec::new();
    let mut has_star = false;
    for (index, projection) in parsed.get_expressions().iter().enumerate() {
        if is_star(projection) {
            has_star = true;
            continue;
        }
        let inner = unaliased(projection)?;
        if is_star(inner) {
            has_star = true;
            continue;
        }
        let Some(output_column) = projection_output_name(projection, index, model.inferred_names)
        else {
            continue;
        };
        let (upstream_columns, confidence) =
            projection_upstream_columns(projection, &alias_map, unqualified)?;
        let transform_kind = classify_transform(inner, &upstream_columns);
        let confidence =
            if !upstream_columns.is_empty() || transform_kind == LineageTransformKind::Constant {
                confidence
            } else {
                LineageConfidence::Unknown
            };
        lineages.push(LineageColumn {
            output_column,
            transform_kind,
            confidence,
            upstream_columns,
        });
    }
    Ok(Some(with_star_columns(lineages, has_star, model, physical)))
}

fn union_lineage(
    parsed: &Expression,
    model: &ParsedModel<'_>,
    physical: &[PhysicalResource],
) -> Result<BuiltLineage, UnreadableExpression> {
    let selects: Vec<Expression> = set_expression_selects(parsed)?;
    if selects.is_empty() {
        return Ok(None);
    }
    let alias_maps: Vec<_> = selects
        .iter()
        .map(|select| table_alias_map(select, physical))
        .collect();
    let max_projection_count = selects
        .iter()
        .map(|select| select.get_expressions().len())
        .max()
        .unwrap_or(0);
    let mut lineages: Vec<LineageColumn> = Vec::new();
    let mut has_star = false;
    for index in 0..max_projection_count {
        let mut output_column = model.inferred_names.get(index).cloned();
        let mut upstream_columns: Vec<LineageSource> = Vec::new();
        let mut seen: HashSet<(LineageResourceType, String, String)> = HashSet::new();
        let mut confidence = LineageConfidence::High;
        let mut transform_kind = LineageTransformKind::Direct;
        for (select, alias_map) in selects.iter().zip(&alias_maps) {
            let Some(projection) = select.get_expressions().get(index) else {
                continue;
            };
            if is_star(projection) {
                has_star = true;
                continue;
            }
            let inner = unaliased(projection)?;
            if is_star(inner) {
                has_star = true;
                continue;
            }
            if output_column.is_none() {
                output_column = projection_output_name(projection, index, model.inferred_names);
            }
            let (branch_upstream, branch_confidence) =
                projection_upstream_columns(projection, alias_map, alias_map.single_resource())?;
            if branch_confidence == LineageConfidence::Unknown {
                confidence = LineageConfidence::Unknown;
            } else if branch_confidence == LineageConfidence::Medium
                && confidence == LineageConfidence::High
            {
                confidence = LineageConfidence::Medium;
            }
            let branch_transform = classify_transform(inner, &branch_upstream);
            if branch_transform != LineageTransformKind::Direct {
                transform_kind = branch_transform;
            }
            for source in branch_upstream {
                let key = (
                    source.resource_type,
                    source.resource_name.clone(),
                    source.column_name.clone(),
                );
                if seen.insert(key) {
                    upstream_columns.push(source);
                }
            }
        }
        let Some(output_column) = output_column else {
            continue;
        };
        if upstream_columns.is_empty() && transform_kind != LineageTransformKind::Constant {
            confidence = LineageConfidence::Unknown;
        }
        lineages.push(LineageColumn {
            output_column,
            transform_kind,
            confidence,
            upstream_columns,
        });
    }
    Ok(Some(with_star_columns(lineages, has_star, model, physical)))
}

fn with_star_columns(
    mut lineages: Vec<LineageColumn>,
    has_star: bool,
    model: &ParsedModel<'_>,
    physical: &[PhysicalResource],
) -> (Vec<LineageColumn>, bool) {
    if has_star {
        let star_columns = star_lineage(
            model.schema,
            physical,
            lineages
                .iter()
                .map(|lineage| lineage.output_column.as_str()),
        );
        lineages.extend(star_columns);
    }
    (lineages, has_star)
}
