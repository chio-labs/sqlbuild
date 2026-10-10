//! Python's re-analysis of a model with its known input shapes, over the crate's query facts.

use std::collections::{HashMap, HashSet};

use polyglot_sql::{AnalyzeQueryOptions, analyze_query};
use serde_json::{Map, Value, json};
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::assembly::analysis_session::_helpers::cte_facts::{
    LegacyAnalysis, LegacyInput, Recovery, RecoveryInput, RecoveryProfile, legacy_analysis,
    recovery,
};
use crate::assembly::analysis_session::_helpers::dict_walk::truthy;
use crate::assembly::analysis_session::_helpers::mappings::ShapeTable;
use crate::assembly::analysis_session::constants::{
    CAST_TRANSFORM, CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_UNKNOWN, FILTER_CONTEXT,
    MAX_FUNCTION_CALL_DEPTH, NON_NULL_NULLABILITY, NULL_KEYWORD, RESOLVED_SOURCE_CONFIDENCE,
    SELECT_SHAPE, SET_OPERATION_SHAPE, TRANSFORM_AGGREGATION, TRANSFORM_CAST, TRANSFORM_CONSTANT,
    TRANSFORM_DIRECT, TRANSFORM_EXPRESSION, TRANSFORM_STAR, UNKNOWN_NULLABILITY, UNKNOWN_TYPE,
    WILDCARD,
};
use crate::assembly::analysis_session::models::{ColumnFact, LineageRow, ModelRequest};
use crate::assembly::analysis_session::types::{NullabilityCallback, Pairs, Shapes};
use crate::semantic_validation::main::normalize::normalize_analysis_sql;
use crate::semantic_validation::models::NormalizationInput;

/// One model's enrichment inputs: the model, its known input shapes and the profile facts.
pub(crate) struct EnrichmentInput<'a> {
    pub(crate) model: &'a ModelRequest,
    pub(crate) input_schemas: &'a Shapes,
    pub(crate) dialect: &'a str,
    pub(crate) function_return_types: &'a Pairs,
    /// Adapter nullability rules by function name.
    pub(crate) nullability_rules: Option<&'a Pairs>,
    pub(crate) nullability_callback: Option<&'a NullabilityCallback>,
}

/// Python's re-analysis: its outcome, columns, plain lineage facts and the star flag.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Enrichment {
    pub(crate) analysis_succeeded: bool,
    pub(crate) columns: Option<Vec<ColumnFact>>,
    pub(crate) lineage: Vec<LineageRow>,
    pub(crate) has_star: bool,
}

/// Python's compact re-analysis: answered, declined to the legacy analysis, or deferred.
enum Projected {
    Native(Enrichment),
    Declined,
    Deferred,
}

/// One projection's upstream sources and confidence code.
type Upstream = (Vec<(String, String, String)>, u8);

/// Python's compact re-analysis, or None where Python would take another path.
pub(crate) fn enrichment(input: &EnrichmentInput<'_>) -> Option<Enrichment> {
    let enrichment: Result<Option<Enrichment>, String> = catch_compiler_panic(|| analysed(input));
    enrichment.unwrap_or_default()
}

/// The re-analysis; Ok(None) where Python takes another path, Err for an unexpected failure.
fn analysed(input: &EnrichmentInput<'_>) -> Result<Option<Enrichment>, String> {
    let normalized: Result<String, _> = normalize_analysis_sql(NormalizationInput {
        sql: input.model.query_sql.clone(),
        dialect: input.dialect.to_owned(),
        stubs: HashMap::new(),
        placeholders: input.model.placeholders.iter().cloned().collect(),
    });
    let cleaned: String = match normalized {
        Ok(cleaned) => cleaned,
        Err(_) => return Ok(None),
    };
    let mut options: Map<String, Value> = Map::new();
    options.insert(
        "dialect".to_owned(),
        Value::String(input.dialect.to_owned()),
    );
    if let Some(schema) = analysis_schema(input) {
        options.insert("schema".to_owned(), schema);
    }
    options.insert(
        "complexityGuard".to_owned(),
        json!({"maxFunctionCallDepth": MAX_FUNCTION_CALL_DEPTH}),
    );
    let options: AnalyzeQueryOptions =
        serde_json::from_value(Value::Object(options)).map_err(|error| error.to_string())?;
    let analysis = match analyze_query(&cleaned, options) {
        Ok(analysis) => analysis,
        Err(_) => return Ok(legacy(input, &cleaned)),
    };
    let analysis: Value = serde_json::to_value(analysis).map_err(|error| error.to_string())?;
    Ok(match projected(input, &analysis, &cleaned) {
        Projected::Native(enrichment) => Some(enrichment),
        Projected::Declined => legacy(input, &cleaned),
        Projected::Deferred => None,
    })
}

/// Python's legacy analysis once compact analysis declines, over the input shapes.
fn legacy(input: &EnrichmentInput<'_>, cleaned: &str) -> Option<Enrichment> {
    let types: ShapeTable = ShapeTable::from_shapes(input.input_schemas);
    let unknown: Shapes = input
        .input_schemas
        .iter()
        .map(|(name, shape)| (name.clone(), unknown_shape(shape)))
        .collect();
    let nullability: ShapeTable = ShapeTable::from_shapes(&unknown);
    let analysis: LegacyAnalysis = match legacy_analysis(&LegacyInput {
        cleaned_sql: cleaned,
        lineage_references: &input.model.lineage_references,
        recover: input.model.recover_cte_facts,
        types: &types,
        nullability: &nullability,
        profile: RecoveryProfile {
            dialect: input.dialect,
            function_return_types: input.function_return_types,
            rules: input.nullability_rules,
            callback: input.nullability_callback,
        },
    }) {
        Ok(analysis) => analysis,
        Err(_deferred) => return None,
    };
    Some(Enrichment {
        analysis_succeeded: analysis.succeeded,
        columns: analysis.columns,
        lineage: analysis.lineage,
        has_star: analysis.has_star,
    })
}

fn unknown_shape(shape: &Pairs) -> Pairs {
    shape
        .iter()
        .map(|(column, _)| (column.clone(), UNKNOWN_NULLABILITY.to_owned()))
        .collect()
}

/// Python's `_compact_analysis_schema` over the input shapes, nullability unknown.
fn analysis_schema(input: &EnrichmentInput<'_>) -> Option<Value> {
    let shapes: HashMap<&str, &Pairs> = input
        .input_schemas
        .iter()
        .map(|(name, shape)| (name.as_str(), shape))
        .collect();
    let mut names: Vec<&str> = input
        .model
        .references
        .iter()
        .map(|reference| reference.analysis_name.as_str())
        .collect::<HashSet<&str>>()
        .into_iter()
        .collect();
    names.sort_unstable();
    let mut tables: Vec<Value> = Vec::new();
    for name in names {
        let Some(shape) = shapes.get(name).filter(|shape| !shape.is_empty()) else {
            continue;
        };
        let columns: Vec<Value> = shape
            .iter()
            .map(|(column, data_type)| json!({"name": column, "type": data_type}))
            .collect();
        tables.push(json!({"name": name, "columns": columns}));
    }
    (!tables.is_empty()).then(|| json!({"tables": tables}))
}

/// Python's projection of `analyze_query` facts into columns and lineage.
fn projected(input: &EnrichmentInput<'_>, analysis: &Value, cleaned: &str) -> Projected {
    let Some(projections) = analysis.get("projections").and_then(Value::as_array) else {
        return Projected::Declined;
    };
    let shape: Option<&str> = analysis.get("shape").and_then(Value::as_str);
    if !matches!(shape, Some(SELECT_SHAPE | SET_OPERATION_SHAPE)) || !eligible(projections) {
        return Projected::Declined;
    }
    match native_projection(input, analysis, cleaned, projections) {
        Some(enrichment) => Projected::Native(enrichment),
        None => Projected::Deferred,
    }
}

/// The compact facts as Python's columns and lineage, None where native defers.
fn native_projection(
    input: &EnrichmentInput<'_>,
    analysis: &Value,
    cleaned: &str,
    projections: &[Value],
) -> Option<Enrichment> {
    let shape: Option<&str> = analysis.get("shape").and_then(Value::as_str);
    let recovery: Recovery = match recovery(&RecoveryInput {
        cleaned_sql: cleaned,
        input_schemas: input.input_schemas,
        recover: recovers_cte_facts(input, analysis),
        null_filter: has_null_filter(analysis),
        profile: RecoveryProfile {
            dialect: input.dialect,
            function_return_types: input.function_return_types,
            rules: input.nullability_rules,
            callback: input.nullability_callback,
        },
    }) {
        Ok(recovery) => recovery,
        Err(_deferred) => return None,
    };
    let resources: HashMap<&str, (&str, &str)> = input
        .model
        .lineage_references
        .iter()
        .map(|(name, kind, resource)| (name.as_str(), (kind.as_str(), resource.as_str())))
        .collect();
    let infer_nullability: bool = shape != Some(SET_OPERATION_SHAPE);
    let mut columns: Vec<ColumnFact> = Vec::new();
    let mut lineage: Vec<LineageRow> = Vec::new();
    for projection in projections {
        let projection: &Map<String, Value> = projection.as_object()?;
        if truthy(projection.get("isStar")) {
            continue;
        }
        let name: &str = text(projection.get("name"));
        if name.is_empty() || name == WILDCARD {
            continue;
        }
        let direct: bool = recovery.direct_outputs.contains(name);
        let data_type: Option<String> = if direct {
            recovered(&recovery.types, name).cloned()
        } else {
            projection_type(projection, input.function_return_types)?
        };
        let nullability: &str = if recovery.non_null_outputs.contains(name) {
            NON_NULL_NULLABILITY
        } else {
            recovered(&recovery.nullability, name)
                .filter(|_| direct)
                .copied()
                .unwrap_or_else(|| projection_nullability(projection, infer_nullability))
        };
        columns.push(ColumnFact {
            name: name.to_owned(),
            data_type,
            nullability: nullability.to_owned(),
        });
        let (sources, confidence) = upstream(projection, &resources);
        let transform: u8 = transform_code(projection, !sources.is_empty());
        lineage.push(LineageRow {
            output_column: name.to_owned(),
            confidence_code: if sources.is_empty() && transform != TRANSFORM_CONSTANT {
                CONFIDENCE_UNKNOWN
            } else {
                confidence
            },
            transform_code: transform,
            sources,
        });
    }
    let has_star: bool = analysis
        .get("starProjections")
        .and_then(Value::as_array)
        .is_some_and(|stars| !stars.is_empty());
    if has_star && input.model.references.len() == 1 {
        let order: HashMap<&str, usize> = declared_order(input);
        let fallback: usize = order.len();
        columns.sort_by_key(|column| order.get(column.name.as_str()).copied().unwrap_or(fallback));
        lineage.sort_by_key(|row| {
            order
                .get(row.output_column.as_str())
                .copied()
                .unwrap_or(fallback)
        });
    }
    Some(Enrichment {
        analysis_succeeded: true,
        columns: Some(columns),
        lineage,
        has_star,
    })
}

/// A recovered fact by exact output name, as Python's dict `get` reads it.
fn recovered<'a, V>(facts: &'a [(String, V)], name: &str) -> Option<&'a V> {
    facts
        .iter()
        .find(|(output, _)| output == name)
        .map(|(_, value)| value)
}

/// Whether Python's CTE pass-through recovery runs past its early return.
fn recovers_cte_facts(input: &EnrichmentInput<'_>, analysis: &Value) -> bool {
    input.model.recover_cte_facts
        && truthy(analysis.get("cteFacts"))
        && !input.input_schemas.is_empty()
}

/// Python's `_compact_analysis_is_eligible` for the projections.
fn eligible(projections: &[Value]) -> bool {
    for projection in projections {
        let Some(projection) = projection.as_object() else {
            return false;
        };
        let cast: bool = text(projection.get("transformKind")) == CAST_TRANSFORM;
        let upstream_empty: bool = projection
            .get("upstream")
            .and_then(Value::as_array)
            .is_none_or(Vec::is_empty);
        if cast && upstream_empty {
            return false;
        }
    }
    true
}

/// Whether a filter reads NULL, where Python parses the query for non-null outputs.
fn has_null_filter(analysis: &Value) -> bool {
    let Some(uses) = analysis.get("columnUses").and_then(Value::as_array) else {
        return false;
    };
    uses.iter().filter_map(Value::as_object).any(|value| {
        text(value.get("context")) == FILTER_CONTEXT
            && text(value.get("expressionSql"))
                .to_uppercase()
                .contains(NULL_KEYWORD)
    })
}

/// Python's `_compact_projection_type`; None where the function name is not ASCII.
fn projection_type(
    projection: &Map<String, Value>,
    function_return_types: &Pairs,
) -> Option<Option<String>> {
    let cast_type: &str = text(projection.get("castType"));
    if !cast_type.is_empty() && cast_type != UNKNOWN_TYPE {
        return Some(Some(cast_type.to_owned()));
    }
    let function_name: Option<&str> = projection
        .get("transformFunction")
        .and_then(Value::as_object)
        .and_then(|function| function.get("name"))
        .and_then(Value::as_str);
    if let Some(function_name) = function_name {
        if !function_name.is_ascii() {
            return None;
        }
        let upper: String = function_name.to_ascii_uppercase();
        if let Some((_, declared)) = function_return_types
            .iter()
            .find(|(name, _)| *name == upper)
        {
            return Some(Some(declared.clone()));
        }
    }
    let type_hint: &str = text(projection.get("typeHint"));
    if !type_hint.is_empty() && type_hint != UNKNOWN_TYPE {
        return Some(Some(type_hint.to_owned()));
    }
    Some(None)
}

fn projection_nullability(projection: &Map<String, Value>, infer: bool) -> &'static str {
    if !infer {
        return UNKNOWN_NULLABILITY;
    }
    match text(projection.get("nullability")) {
        "non_null" => "non_null",
        "nullable" => "nullable",
        _ => UNKNOWN_NULLABILITY,
    }
}

/// Python's `_compact_lineage_upstream_columns`.
fn upstream(projection: &Map<String, Value>, resources: &HashMap<&str, (&str, &str)>) -> Upstream {
    let Some(values) = projection.get("upstream").and_then(Value::as_array) else {
        return (Vec::new(), CONFIDENCE_UNKNOWN);
    };
    let mut sources: Vec<(String, String, String)> = Vec::new();
    let mut seen: HashSet<(String, String, String)> = HashSet::new();
    let mut confidence: u8 = CONFIDENCE_HIGH;
    for value in values.iter().filter_map(Value::as_object) {
        let column: &str = text(value.get("column"));
        if column.is_empty() || column == WILDCARD {
            continue;
        }
        let mut source_name: &str = text(value.get("sourceName"));
        if source_name.is_empty() {
            source_name = text(value.get("table"));
        }
        if source_name.is_empty() {
            confidence = CONFIDENCE_UNKNOWN;
            continue;
        }
        let Some((kind, resource)) = resources.get(source_name) else {
            continue;
        };
        let resolved: bool = text(value.get("confidence")) == RESOLVED_SOURCE_CONFIDENCE;
        let aliased: bool = value.get("sourceAlias").is_some_and(Value::is_string);
        if !resolved && !aliased {
            confidence = CONFIDENCE_MEDIUM;
        }
        let key = (
            (*kind).to_owned(),
            (*resource).to_owned(),
            column.to_owned(),
        );
        if seen.insert(key.clone()) {
            sources.push(key);
        }
    }
    sources.sort();
    (sources, confidence)
}

/// Python's `_compact_transform_kind` as a compact code.
fn transform_code(projection: &Map<String, Value>, has_upstream: bool) -> u8 {
    match text(projection.get("transformKind")) {
        "star" => TRANSFORM_STAR,
        "cast" => TRANSFORM_CAST,
        "aggregation" => TRANSFORM_AGGREGATION,
        "constant" => TRANSFORM_CONSTANT,
        _ if !has_upstream => TRANSFORM_CONSTANT,
        "direct" => TRANSFORM_DIRECT,
        _ => TRANSFORM_EXPRESSION,
    }
}

/// The declared column order of the model's single reference, from its input shape.
fn declared_order<'a>(input: &EnrichmentInput<'a>) -> HashMap<&'a str, usize> {
    let Some(reference) = input.model.references.first() else {
        return HashMap::new();
    };
    let Some((_, shape)) = input
        .input_schemas
        .iter()
        .find(|(name, _)| *name == reference.analysis_name)
    else {
        return HashMap::new();
    };
    let mut order: HashMap<&str, usize> = HashMap::new();
    for (index, (column, _)) in shape.iter().enumerate() {
        order.entry(column.as_str()).or_insert(index);
    }
    order
}

/// Python's `str(value or "")` for the string fields this projection reads.
fn text(value: Option<&Value>) -> &str {
    value.and_then(Value::as_str).unwrap_or_default()
}
