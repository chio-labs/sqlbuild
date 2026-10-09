//! One compact analysis batch built, run and projected exactly as Python's unshared batch.

use std::collections::{HashMap, HashSet};

use serde_json::{Map, Value, json};

use crate::assembly::analysis_session::_helpers::catalog_state::SessionCatalog;
use crate::assembly::analysis_session::_helpers::mappings::{ShapeTable, native_dialect};
use crate::assembly::analysis_session::constants::{
    BINDING_SEVERITIES, COMPACT_WORKERS, CONFIDENCE_CODES, DEFAULT_BINDING_MESSAGE, FACT_LENGTH,
    INVALID_NATIVE_RESPONSE, LEGACY_FALLBACK, LEGACY_RESPONSE_LENGTH, NULLABILITY_BY_CODE,
    RESPONSE_LENGTH, SOURCE_LENGTH, TRANSFORM_CODES,
};
use crate::assembly::analysis_session::models::{ColumnFact, LineageRow};
use crate::assembly::analysis_session::types::{Pairs, Shapes};
use crate::semantic_validation::main::diagnostics::binding_diagnostics;
use crate::semantic_validation::types::{DiagnosticRow, NormalizationRequest};

const INVALID_BATCH: &str = "native compact query analysis returned an invalid batch response";
const INVALID_TEMPLATE: &str = "native compact query analysis returned an invalid template";
const INVALID_COLUMN: &str = "native compact analysis returned invalid column facts";

/// One query of a batch with the facts Python's preparation reads.
pub(crate) struct BatchMember<'a> {
    pub(crate) query_sql: &'a str,
    pub(crate) placeholders: &'a Pairs,
    /// Every reference's analysis name, in reference order.
    pub(crate) analysis_names: Vec<&'a str>,
    pub(crate) lineage_references: &'a [(String, String, String)],
    pub(crate) recover_cte_facts: bool,
    pub(crate) binding_schema: Option<&'a Shapes>,
}

/// One batch with the inference profile settings and relation facts its analysis reads.
pub(crate) struct Batch<'a> {
    pub(crate) dialect: &'a str,
    pub(crate) function_return_types: &'a Pairs,
    pub(crate) rich_type_inference: bool,
    pub(crate) members: Vec<BatchMember<'a>>,
    pub(crate) types: &'a ShapeTable,
    pub(crate) nullability: &'a ShapeTable,
}

/// What the native engine returned for one member.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum MemberAnalysis {
    Projected {
        columns: Vec<ColumnFact>,
        lineage: Vec<LineageRow>,
        has_star: bool,
        star_resolved: bool,
    },
    /// Analysis failed; Python records an unsuccessful analysis.
    Failed,
    /// The engine asked for Python's legacy analysis, keeping lineage rows when it had them.
    Legacy { lineage: Option<Vec<LineageRow>> },
}

/// One member's projected native analysis.
#[derive(Debug, Clone)]
pub(crate) struct MemberResult {
    pub(crate) cleaned_sql: String,
    pub(crate) analysis: MemberAnalysis,
    pub(crate) binding_diagnostics: Option<Vec<DiagnosticRow>>,
    /// The failure Python logs at debug level.
    pub(crate) failure: Option<String>,
}

/// The batch's response tables Python's projection reads.
struct BatchResponse<'a> {
    strings: Vec<&'a str>,
    facts: &'a [Value],
    templates: &'a [Value],
}

/// The prepared request and each member's query index.
struct BatchPayload {
    request: Value,
    query_indexes: Vec<usize>,
}

impl SessionCatalog {
    /// Normalize, prepare, analyse and project a batch; an error is the one Python raises.
    pub(crate) fn analyze_batch(&mut self, batch: &Batch<'_>) -> Result<Vec<MemberResult>, String> {
        if batch.members.is_empty() {
            return Ok(Vec::new());
        }
        let mut required: Vec<String> = Vec::new();
        let mut seen: HashSet<&str> = HashSet::new();
        for name in batch
            .members
            .iter()
            .flat_map(|member| member.analysis_names.iter())
        {
            if seen.insert(name) {
                required.push((*name).to_owned());
            }
        }
        self.prepare_analysis(&required, batch.types, batch.nullability);
        let cleaned: Vec<String> = self.normalize_members(batch)?;
        let payload: BatchPayload = self.batch_payload(batch, &cleaned)?;
        let job = self.native.prepare_compact(&payload.request.to_string())?;
        let analysis = job
            .take_analysis()
            .ok_or("compact analysis job already ran")?;
        let response: Value =
            serde_json::from_str(&job.run(analysis)?).map_err(|error| error.to_string())?;
        let results: Vec<MemberResult> = attach_validations(
            &response,
            &payload.query_indexes,
            batch.dialect,
            project_response(&response, cleaned)?,
        )?;
        self.with_separate_validation(&batch.members, results)
    }

    fn normalize_members(&self, batch: &Batch<'_>) -> Result<Vec<String>, String> {
        let requests: Vec<NormalizationRequest> = batch
            .members
            .iter()
            .map(|member| {
                (
                    member.query_sql.to_owned(),
                    HashMap::new(),
                    member.placeholders.iter().cloned().collect(),
                )
            })
            .collect();
        self.native
            .normalize_analysis_sqls(batch.dialect, requests)?
            .into_iter()
            .collect()
    }

    /// Python's `_prepare_compact_analysis_batch` request and each member's query index.
    fn batch_payload(
        &mut self,
        batch: &Batch<'_>,
        cleaned: &[String],
    ) -> Result<BatchPayload, String> {
        let function_return_types: Map<String, Value> = batch
            .function_return_types
            .iter()
            .map(|(name, value)| (name.clone(), Value::String(value.clone())))
            .collect();
        let mut queries: Vec<Value> = Vec::new();
        let mut query_keys: HashMap<String, usize> = HashMap::new();
        let mut templates: Vec<Value> = Vec::new();
        let mut template_keys: HashMap<String, usize> = HashMap::new();
        let mut projections: Vec<Value> = Vec::with_capacity(batch.members.len());
        let mut query_indexes: Vec<usize> = Vec::with_capacity(batch.members.len());
        for (member, sql) in batch.members.iter().zip(cleaned) {
            let query: Value = self.member_query(batch.dialect, member, sql)?;
            let query_index: usize = *query_keys.entry(query.to_string()).or_insert_with(|| {
                queries.push(query);
                queries.len() - 1
            });
            query_indexes.push(query_index);
            let template: Value = json!({
                "queryIndex": query_index,
                "references": lineage_resources(member),
                "functionReturnTypes": function_return_types,
                "declaredColumnOrder": declared_column_order(member, batch.nullability),
                "recoverCteFacts": member.recover_cte_facts,
                "richTypeInference": batch.rich_type_inference,
            });
            let template_index: usize =
                *template_keys
                    .entry(template.to_string())
                    .or_insert_with(|| {
                        templates.push(template);
                        templates.len() - 1
                    });
            let resource_names: Map<String, Value> = member
                .lineage_references
                .iter()
                .map(|(name, _, resource)| (name.clone(), Value::String(resource.clone())))
                .collect();
            projections
                .push(json!({"templateIndex": template_index, "resourceNames": resource_names}));
        }
        Ok(BatchPayload {
            request: json!({
                "queries": queries,
                "templates": templates,
                "projections": projections,
                "workers": COMPACT_WORKERS,
            }),
            query_indexes,
        })
    }

    /// One member's query: analysis references and, when bound, its catalog binding.
    fn member_query(
        &mut self,
        dialect: &str,
        member: &BatchMember<'_>,
        sql: &str,
    ) -> Result<Value, String> {
        let mut lineage_names: Vec<&str> = member
            .lineage_references
            .iter()
            .map(|(name, _, _)| name.as_str())
            .collect();
        lineage_names.sort_unstable();
        let analysis_references: Vec<[&str; 2]> =
            lineage_names.iter().map(|name| [*name, *name]).collect();
        let mut query: Value = json!({
            "sql": sql,
            "dialect": dialect,
            "analysis_references": analysis_references,
        });
        match member.binding_schema {
            Some(schema) => {
                let (_, references, overrides) = self
                    .prepare(&[(sql, schema)])
                    .pop()
                    .ok_or("binding preparation returned no request")?;
                query["binding_references"] = json!(references);
                if !overrides.is_empty() {
                    query["binding_override"] = json!(self.register_override(overrides));
                }
            }
            None if !member.lineage_references.is_empty() => {
                return Err("unbound members with relations are not supported".to_owned());
            }
            None => {}
        }
        Ok(query)
    }

    /// Python's separate schema validation for bound members the batch did not validate.
    fn with_separate_validation(
        &mut self,
        members: &[BatchMember<'_>],
        mut results: Vec<MemberResult>,
    ) -> Result<Vec<MemberResult>, String> {
        let mut indexes: Vec<usize> = Vec::new();
        let mut requests: Vec<(&str, &Shapes)> = Vec::new();
        for (index, (member, result)) in members.iter().zip(&results).enumerate() {
            if let (Some(schema), None) = (member.binding_schema, &result.binding_diagnostics) {
                indexes.push(index);
                requests.push((result.cleaned_sql.as_str(), schema));
            }
        }
        if indexes.is_empty() {
            return Ok(results);
        }
        let prepared: Vec<_> = self.prepare(&requests);
        let rows: Vec<Vec<DiagnosticRow>> = self.native.binding_results(prepared)?;
        if rows.len() != indexes.len() {
            return Err(
                "native SQL schema validation returned an invalid batch response".to_owned(),
            );
        }
        for (index, diagnostics) in indexes.into_iter().zip(rows) {
            results[index].binding_diagnostics = Some(diagnostics);
        }
        Ok(results)
    }
}

fn lineage_resources(member: &BatchMember<'_>) -> Map<String, Value> {
    member
        .lineage_references
        .iter()
        .map(|(name, resource_type, _)| {
            (
                name.clone(),
                json!({"resourceType": resource_type, "resourceName": name}),
            )
        })
        .collect()
}

/// A single-reference member's declared column order, as Python's template records it.
fn declared_column_order<'a>(
    member: &BatchMember<'_>,
    nullability: &'a ShapeTable,
) -> Vec<&'a str> {
    let [single] = member.analysis_names.as_slice() else {
        return Vec::new();
    };
    let Some(columns) = nullability.get(single) else {
        return Vec::new();
    };
    columns.iter().map(|(name, _)| name.as_str()).collect()
}

fn to_index(value: u64) -> Result<usize, String> {
    usize::try_from(value).map_err(|error| error.to_string())
}

/// Python's `_project_compact_analysis_batch`.
fn project_response(response: &Value, cleaned: Vec<String>) -> Result<Vec<MemberResult>, String> {
    let strings: Vec<&str> = response
        .get("strings")
        .and_then(Value::as_array)
        .ok_or(INVALID_BATCH)?
        .iter()
        .map(|value| value.as_str().ok_or(INVALID_BATCH))
        .collect::<Result<_, _>>()?;
    let batch = BatchResponse {
        strings,
        facts: response
            .get("facts")
            .and_then(Value::as_array)
            .ok_or(INVALID_BATCH)?,
        templates: response
            .get("templates")
            .and_then(Value::as_array)
            .ok_or(INVALID_BATCH)?,
    };
    let analyses = response
        .get("analyses")
        .and_then(Value::as_array)
        .filter(|analyses| analyses.len() == cleaned.len())
        .ok_or(INVALID_BATCH)?;
    let mut results: Vec<MemberResult> = Vec::with_capacity(cleaned.len());
    for (cleaned_sql, analysis) in cleaned.into_iter().zip(analyses) {
        let (analysis, failure) = project_member(&batch, analysis)?;
        results.push(MemberResult {
            cleaned_sql,
            analysis,
            binding_diagnostics: None,
            failure,
        });
    }
    Ok(results)
}

fn project_member(
    batch: &BatchResponse<'_>,
    analysis: &Value,
) -> Result<(MemberAnalysis, Option<String>), String> {
    let entry: Option<&Vec<Value>> = analysis
        .as_array()
        .filter(|entry| entry.len() == RESPONSE_LENGTH);
    let (Some(template_index), Some(mappings)) = (
        entry.and_then(|entry| entry[0].as_i64()),
        entry.and_then(|entry| entry[1].as_array()),
    ) else {
        return Ok((
            MemberAnalysis::Failed,
            Some(INVALID_NATIVE_RESPONSE.to_owned()),
        ));
    };
    let template: &Value = u64::try_from(template_index)
        .map_err(|error| error.to_string())
        .and_then(to_index)
        .map(|index| batch.templates.get(index))?
        .ok_or("native compact query analysis returned an invalid template index")?;
    if let Some(error) = template.as_str() {
        let analysis = if error == LEGACY_FALLBACK {
            MemberAnalysis::Legacy { lineage: None }
        } else {
            MemberAnalysis::Failed
        };
        return Ok((analysis, Some(error.to_owned())));
    }
    let parts: &Vec<Value> = template.as_array().ok_or(INVALID_TEMPLATE)?;
    let flagged: bool = parts.len() == LEGACY_RESPONSE_LENGTH;
    let legacy: bool = flagged && parts[2].as_str() == Some(LEGACY_FALLBACK);
    let (Some(rows), Some(has_star)) = (
        parts.first().and_then(Value::as_array),
        parts.get(1).and_then(Value::as_bool),
    ) else {
        return Err(INVALID_TEMPLATE.to_owned());
    };
    if !(parts.len() == RESPONSE_LENGTH || legacy || (flagged && parts[2].is_boolean())) {
        return Err(INVALID_TEMPLATE.to_owned());
    }
    let resource_indexes: HashMap<u64, u64> = resource_name_indexes(batch, mappings)?;
    let (columns, lineage) = project_rows(batch, rows, &resource_indexes)?;
    if legacy {
        return Ok((
            MemberAnalysis::Legacy {
                lineage: Some(lineage),
            },
            None,
        ));
    }
    Ok((
        MemberAnalysis::Projected {
            columns,
            lineage,
            has_star,
            star_resolved: flagged && parts[2].as_bool() == Some(true),
        },
        None,
    ))
}

fn resource_name_indexes(
    batch: &BatchResponse<'_>,
    mappings: &[Value],
) -> Result<HashMap<u64, u64>, String> {
    let mut indexes: HashMap<u64, u64> = HashMap::new();
    for mapping in mappings {
        let pair: &Vec<Value> = mapping
            .as_array()
            .filter(|pair| pair.len() == RESPONSE_LENGTH)
            .ok_or("native compact query analysis returned an invalid resource mapping")?;
        let (Some(canonical), Some(resource)) = (pair[0].as_u64(), pair[1].as_u64()) else {
            return Err(
                "native compact query analysis returned an invalid resource mapping".to_owned(),
            );
        };
        ensure_pooled(batch, canonical)?;
        ensure_pooled(batch, resource)?;
        indexes.insert(canonical, resource);
    }
    Ok(indexes)
}

fn pooled<'a>(batch: &BatchResponse<'a>, index: u64) -> Result<&'a str, String> {
    batch
        .strings
        .get(to_index(index)?)
        .copied()
        .ok_or_else(|| "native compact analysis returned an out-of-range index".to_owned())
}

fn ensure_pooled(batch: &BatchResponse<'_>, index: u64) -> Result<(), String> {
    pooled(batch, index).map(drop)
}

/// Python's `_compact_projected_analysis_result` columns and resolved lineage rows.
fn project_rows(
    batch: &BatchResponse<'_>,
    rows: &[Value],
    resource_indexes: &HashMap<u64, u64>,
) -> Result<(Vec<ColumnFact>, Vec<LineageRow>), String> {
    let mut columns: Vec<ColumnFact> = Vec::with_capacity(rows.len());
    let mut lineage: Vec<LineageRow> = Vec::with_capacity(rows.len());
    for row in rows {
        let fact: &Vec<Value> = batch
            .facts
            .get(to_index(row.as_u64().ok_or(INVALID_COLUMN)?)?)
            .and_then(Value::as_array)
            .filter(|fact| fact.len() == FACT_LENGTH)
            .ok_or("native compact analysis returned an invalid column")?;
        let (column, lineage_row) = project_fact(batch, fact, resource_indexes)?;
        columns.push(column);
        lineage.push(lineage_row);
    }
    Ok((columns, lineage))
}

fn project_fact(
    batch: &BatchResponse<'_>,
    fact: &[Value],
    resource_indexes: &HashMap<u64, u64>,
) -> Result<(ColumnFact, LineageRow), String> {
    let (Some(name), Some(nullability), Some(transform), Some(confidence), Some(sources)) = (
        fact[0].as_u64(),
        fact[2].as_u64(),
        fact[3].as_u64(),
        fact[4].as_u64(),
        fact[5].as_array(),
    ) else {
        return Err(INVALID_COLUMN.to_owned());
    };
    let nullability: &str = NULLABILITY_BY_CODE
        .get(to_index(nullability)?)
        .copied()
        .filter(|_| transform < TRANSFORM_CODES && confidence < CONFIDENCE_CODES)
        .ok_or("native compact analysis returned an invalid fact code")?;
    let data_type: Option<String> = match &fact[1] {
        Value::Null => None,
        value => Some(
            pooled(
                batch,
                value
                    .as_u64()
                    .ok_or("native compact analysis returned an invalid type index")?,
            )?
            .to_owned(),
        ),
    };
    let output_column: String = pooled(batch, name)?.to_owned();
    let mut resolved: Vec<(String, String, String)> = Vec::with_capacity(sources.len());
    for source in sources {
        resolved.push(project_source(batch, source, resource_indexes)?);
    }
    Ok((
        ColumnFact {
            name: output_column.clone(),
            data_type,
            nullability: nullability.to_owned(),
        },
        LineageRow {
            output_column,
            transform_code: u8::try_from(transform).map_err(|error| error.to_string())?,
            confidence_code: u8::try_from(confidence).map_err(|error| error.to_string())?,
            sources: resolved,
        },
    ))
}

fn project_source(
    batch: &BatchResponse<'_>,
    source: &Value,
    resource_indexes: &HashMap<u64, u64>,
) -> Result<(String, String, String), String> {
    const INVALID_SOURCE: &str = "native compact analysis returned invalid upstream lineage";
    let parts: &Vec<Value> = source
        .as_array()
        .filter(|parts| parts.len() == SOURCE_LENGTH)
        .ok_or(INVALID_SOURCE)?;
    let (Some(resource_type), Some(resource), Some(column)) =
        (parts[0].as_u64(), parts[1].as_u64(), parts[2].as_u64())
    else {
        return Err(INVALID_SOURCE.to_owned());
    };
    ensure_pooled(batch, resource)?;
    Ok((
        pooled(batch, resource_type)?.to_owned(),
        pooled(
            batch,
            resource_indexes.get(&resource).copied().unwrap_or(resource),
        )?
        .to_owned(),
        pooled(batch, column)?.to_owned(),
    ))
}

/// Python's `_attach_compiled_bindings`: decode the batch's fused binding validations.
fn attach_validations(
    response: &Value,
    query_indexes: &[usize],
    dialect: &str,
    mut results: Vec<MemberResult>,
) -> Result<Vec<MemberResult>, String> {
    let Some(validations) = response.get("validations").filter(|value| !value.is_null()) else {
        return Ok(results);
    };
    let query_count: usize = query_indexes.iter().max().map_or(0, |index| index + 1);
    let validations: &Vec<Value> = validations
        .as_array()
        .filter(|validations| validations.len() == query_count)
        .ok_or("native compilation returned an invalid binding batch")?;
    for (result, query_index) in results.iter_mut().zip(query_indexes) {
        let validation: &Value = &validations[*query_index];
        if !validation.is_null() {
            result.binding_diagnostics =
                Some(decode_validation(&result.cleaned_sql, dialect, validation)?);
        }
    }
    Ok(results)
}

/// Python's `_binding_result` over one native validation.
fn decode_validation(
    sql: &str,
    dialect: &str,
    validation: &Value,
) -> Result<Vec<DiagnosticRow>, String> {
    let errors: &Vec<Value> = validation
        .get("errors")
        .and_then(Value::as_array)
        .ok_or("native SQL schema validation returned an invalid response")?;
    let mut rows: Vec<DiagnosticRow> = Vec::new();
    for error in errors {
        if let Some(row) = diagnostic_row(error)? {
            rows.push(row);
        }
    }
    binding_diagnostics(sql, native_dialect(dialect), rows)
}

fn diagnostic_row(error: &Value) -> Result<Option<DiagnosticRow>, String> {
    let (Some(severity), Some(code)) = (
        error.get("severity").and_then(Value::as_str),
        error.get("code").and_then(Value::as_str),
    ) else {
        return Ok(None);
    };
    if !BINDING_SEVERITIES.contains(&severity) {
        return Ok(None);
    }
    let message: String = match error.get("message") {
        Some(Value::String(message)) if !message.is_empty() => message.clone(),
        _ => DEFAULT_BINDING_MESSAGE.to_owned(),
    };
    Ok(Some((
        code.to_owned(),
        message,
        position(error, "line")?,
        position(error, "column")?,
        position(error, "start")?,
        position(error, "end")?,
        severity.to_owned(),
    )))
}

fn position(error: &Value, key: &str) -> Result<Option<usize>, String> {
    error
        .get(key)
        .and_then(Value::as_u64)
        .map(to_index)
        .transpose()
}
