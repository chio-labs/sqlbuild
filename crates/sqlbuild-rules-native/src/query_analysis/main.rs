//! Coarse, bounded native batch boundary for compact SQL query analysis.

use polyglot_sql::{
    AnalyzeQueryOptions, DialectType, ProjectionNullability, QueryAnalysis, QueryShape,
    ReferenceConfidence, TransformKind, ValidationSchema, analyze_query,
    analyze_query_for_project_projections,
};
use rayon::iter::{IntoParallelIterator, ParallelIterator};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

use crate::constants::{SQL_WILDCARD, UNKNOWN_SQL_TYPE, VARCHAR_SQL_TYPE};

const DEFAULT_WORKERS: usize = 4;
const MAX_WORKERS: usize = 4;
const ANALYSIS_WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;

#[derive(Debug, Deserialize)]
struct AnalysisBatchRequest {
    requests: Vec<AnalysisRequest>,
    #[serde(default = "default_workers")]
    workers: usize,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct AnalysisRequest {
    sql: String,
    #[serde(default = "default_dialect")]
    dialect: String,
    #[serde(default)]
    schema: Option<ValidationSchema>,
}

#[derive(Debug, Serialize)]
#[serde(untagged)]
enum AnalysisResponse {
    Success { analysis: QueryAnalysis },
    Failure { error: String },
}

#[derive(Debug, Deserialize)]
struct ProjectAnalysisBatchRequest {
    requests: Vec<ProjectAnalysisRequest>,
    #[serde(default = "default_workers")]
    workers: usize,
}

#[derive(Debug, Deserialize)]
struct CompactProjectAnalysisBatchRequest {
    queries: Vec<AnalysisRequest>,
    templates: Vec<CompactProjectAnalysisTemplateRequest>,
    projections: Vec<CompactProjectAnalysisProjectionRequest>,
    #[serde(default = "default_workers")]
    workers: usize,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CompactProjectAnalysisTemplateRequest {
    query_index: usize,
    #[serde(default)]
    references: HashMap<String, LineageResource>,
    #[serde(default)]
    function_return_types: HashMap<String, String>,
    #[serde(default)]
    declared_column_order: Vec<String>,
    #[serde(default)]
    recover_cte_facts: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CompactProjectAnalysisProjectionRequest {
    template_index: usize,
    #[serde(default)]
    resource_names: HashMap<String, String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProjectAnalysisRequest {
    #[serde(flatten)]
    query: AnalysisRequest,
    #[serde(default)]
    references: HashMap<String, LineageResource>,
    #[serde(default)]
    function_return_types: HashMap<String, String>,
    #[serde(default)]
    declared_column_order: Vec<String>,
    #[serde(default)]
    recover_cte_facts: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct LineageResource {
    resource_type: String,
    resource_name: String,
}

#[derive(Debug, Serialize)]
#[serde(untagged)]
enum ProjectAnalysisResponse {
    Success { analysis: ProjectAnalysis },
    Failure { error: String },
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProjectAnalysis {
    columns: Vec<ProjectColumn>,
    lineage_columns: Vec<ProjectLineageColumn>,
    has_star: bool,
}

struct ProjectAnalysisInputs<'a> {
    analysis: &'a QueryAnalysis,
    references: &'a HashMap<String, LineageResource>,
    function_return_types: &'a HashMap<String, String>,
    declared_column_order: &'a [String],
    recover_cte_facts: bool,
}

struct ProjectAnalysisProjection {
    analysis_index: usize,
    references: HashMap<String, LineageResource>,
    function_return_types: HashMap<String, String>,
    declared_column_order: Vec<String>,
    recover_cte_facts: bool,
}

struct ProjectAnalysisProjectionResult {
    projection_index: usize,
    resource_names: Vec<(String, String)>,
}

#[derive(Debug, Serialize)]
struct ProjectColumn {
    name: String,
    #[serde(rename = "type")]
    data_type: Option<String>,
    nullability: ProjectNullability,
}

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
enum ProjectNullability {
    NonNull,
    Nullable,
    Unknown,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProjectLineageColumn {
    output_column: String,
    upstream_columns: Vec<ProjectLineageSource>,
    transform_kind: ProjectTransformKind,
    confidence: ProjectConfidence,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProjectLineageSource {
    resource_type: String,
    resource_name: String,
    column_name: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum ProjectTransformKind {
    Direct,
    Cast,
    Expression,
    Aggregation,
    Star,
    Constant,
}

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
enum ProjectConfidence {
    High,
    Medium,
    Unknown,
}

fn default_workers() -> usize {
    DEFAULT_WORKERS
}

fn default_dialect() -> String {
    "generic".to_string()
}

pub(crate) fn analyze_json(request_json: &str) -> Result<String, String> {
    let request: AnalysisBatchRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let workers = request.workers.clamp(1, MAX_WORKERS);
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(workers.min(request.requests.len().max(1)))
        .stack_size(ANALYSIS_WORKER_STACK_BYTES)
        .build()
        .map_err(|error| error.to_string())?;
    let responses: Vec<AnalysisResponse> = pool.install(|| {
        request
            .requests
            .into_par_iter()
            .map(analyze_request)
            .collect()
    });
    serde_json::to_string(&responses).map_err(|error| error.to_string())
}

pub(crate) fn analyze_project_json(request_json: &str) -> Result<String, String> {
    let request: ProjectAnalysisBatchRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let workers = request.workers.clamp(1, MAX_WORKERS);
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(workers.min(request.requests.len().max(1)))
        .stack_size(ANALYSIS_WORKER_STACK_BYTES)
        .build()
        .map_err(|error| error.to_string())?;
    let responses: Vec<ProjectAnalysisResponse> = pool.install(|| {
        request
            .requests
            .into_par_iter()
            .map(analyze_project_request)
            .collect()
    });
    serde_json::to_string(&responses).map_err(|error| error.to_string())
}

pub(crate) fn analyze_project_compact_json(request_json: &str) -> Result<String, String> {
    let request: CompactProjectAnalysisBatchRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let workers = request.workers.clamp(1, MAX_WORKERS);
    if request
        .templates
        .iter()
        .any(|template| template.query_index >= request.queries.len())
    {
        return Err("compact project analysis received an invalid query index".to_string());
    }
    if request
        .projections
        .iter()
        .any(|projection| projection.template_index >= request.templates.len())
    {
        return Err("compact project analysis received an invalid template index".to_string());
    }
    let unique_query_count = request.queries.len();
    let unique_projection_count = request.templates.len();
    let unique_projections: Vec<ProjectAnalysisProjection> = request
        .templates
        .into_iter()
        .map(|template| ProjectAnalysisProjection {
            analysis_index: template.query_index,
            references: template.references,
            function_return_types: template.function_return_types,
            declared_column_order: template.declared_column_order,
            recover_cte_facts: template.recover_cte_facts,
        })
        .collect();
    let projection_results: Vec<ProjectAnalysisProjectionResult> = request
        .projections
        .into_iter()
        .map(|projection| {
            let mut resource_names: Vec<(String, String)> =
                projection.resource_names.into_iter().collect();
            resource_names.sort();
            ProjectAnalysisProjectionResult {
                projection_index: projection.template_index,
                resource_names,
            }
        })
        .collect();
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(workers.min(unique_query_count.max(1)))
        .stack_size(ANALYSIS_WORKER_STACK_BYTES)
        .build()
        .map_err(|error| error.to_string())?;
    let query_analyses: Vec<Result<QueryAnalysis, String>> = pool.install(|| {
        request
            .queries
            .into_par_iter()
            .map(|query| query_analysis(query, true))
            .collect()
    });
    let analyses: Vec<Result<ProjectAnalysis, String>> = pool.install(|| {
        unique_projections
            .into_par_iter()
            .map(|projection| {
                let analysis = query_analyses[projection.analysis_index]
                    .as_ref()
                    .map_err(Clone::clone)?;
                Ok(project_analysis(ProjectAnalysisInputs {
                    analysis,
                    references: &projection.references,
                    function_return_types: &projection.function_return_types,
                    declared_column_order: &projection.declared_column_order,
                    recover_cte_facts: projection.recover_cte_facts,
                }))
            })
            .collect()
    });
    serde_json::to_string(&compact_project_batch(
        analyses,
        projection_results,
        unique_query_count,
        unique_projection_count,
    ))
    .map_err(|error| error.to_string())
}

fn analyze_request(request: AnalysisRequest) -> AnalysisResponse {
    match query_analysis(request, false) {
        Ok(analysis) => AnalysisResponse::Success { analysis },
        Err(error) => AnalysisResponse::Failure { error },
    }
}

fn query_analysis(
    request: AnalysisRequest,
    project_projections: bool,
) -> Result<QueryAnalysis, String> {
    let dialect: DialectType = match request.dialect.parse() {
        Ok(dialect) => dialect,
        Err(error) => {
            return Err(format!(
                "unsupported Polyglot dialect '{}': {error}",
                request.dialect
            ));
        }
    };
    let options = AnalyzeQueryOptions {
        complexity_guard: None,
        dialect,
        schema: request.schema,
    };
    if project_projections {
        analyze_query_for_project_projections(&request.sql, options)
    } else {
        analyze_query(&request.sql, options)
    }
    .map_err(|error| error.to_string())
}

fn analyze_project_request(request: ProjectAnalysisRequest) -> ProjectAnalysisResponse {
    match analyze_project_result(request) {
        Ok(analysis) => ProjectAnalysisResponse::Success { analysis },
        Err(error) => ProjectAnalysisResponse::Failure { error },
    }
}

fn analyze_project_result(request: ProjectAnalysisRequest) -> Result<ProjectAnalysis, String> {
    let analysis = query_analysis(request.query, true)?;
    Ok(project_analysis(ProjectAnalysisInputs {
        analysis: &analysis,
        references: &request.references,
        function_return_types: &request.function_return_types,
        declared_column_order: &request.declared_column_order,
        recover_cte_facts: request.recover_cte_facts,
    }))
}

type CompactProjectColumn = (usize, Option<usize>, u8, u8, u8, Vec<(usize, usize, usize)>);

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct CompactProjectBatch {
    strings: Vec<String>,
    facts: Vec<CompactProjectColumn>,
    templates: Vec<CompactProjectResponse>,
    analyses: Vec<CompactProjectProjection>,
    unique_query_count: usize,
    unique_projection_count: usize,
}

#[derive(Debug, Serialize)]
#[serde(untagged)]
enum CompactProjectResponse {
    Success((Vec<usize>, bool)),
    Failure(String),
}

type CompactProjectProjection = (usize, Vec<(usize, usize)>);

#[derive(Default)]
struct StringInterner {
    strings: Vec<String>,
    indexes: HashMap<String, usize>,
}

impl StringInterner {
    fn intern(&mut self, value: String) -> usize {
        if let Some(index) = self.indexes.get(&value) {
            return *index;
        }
        let index = self.strings.len();
        self.indexes.insert(value.clone(), index);
        self.strings.push(value);
        index
    }
}

fn compact_project_batch(
    analyses: Vec<Result<ProjectAnalysis, String>>,
    projections: Vec<ProjectAnalysisProjectionResult>,
    unique_query_count: usize,
    unique_projection_count: usize,
) -> CompactProjectBatch {
    let mut interner = StringInterner::default();
    let mut facts: Vec<CompactProjectColumn> = Vec::new();
    let mut fact_indexes: HashMap<CompactProjectColumn, usize> = HashMap::new();
    let mut templates: Vec<CompactProjectResponse> = Vec::with_capacity(analyses.len());
    for result in analyses {
        let analysis = match result {
            Ok(analysis) => analysis,
            Err(error) => {
                templates.push(CompactProjectResponse::Failure(error));
                continue;
            }
        };
        let mut columns = Vec::with_capacity(analysis.columns.len());
        for (column, lineage) in analysis.columns.into_iter().zip(analysis.lineage_columns) {
            let upstream: Vec<(usize, usize, usize)> = lineage
                .upstream_columns
                .into_iter()
                .map(|source| {
                    (
                        interner.intern(source.resource_type),
                        interner.intern(source.resource_name),
                        interner.intern(source.column_name),
                    )
                })
                .collect();
            let fact = (
                interner.intern(column.name),
                column.data_type.map(|value| interner.intern(value)),
                nullability_code(column.nullability),
                transform_code(lineage.transform_kind),
                confidence_code(lineage.confidence),
                upstream,
            );
            let next_index = facts.len();
            let fact_index = *fact_indexes.entry(fact.clone()).or_insert_with(|| {
                facts.push(fact);
                next_index
            });
            columns.push(fact_index);
        }
        templates.push(CompactProjectResponse::Success((
            columns,
            analysis.has_star,
        )));
    }
    let mut compact_projections: Vec<CompactProjectProjection> =
        Vec::with_capacity(projections.len());
    for projection in projections {
        let mut resource_names: Vec<(usize, usize)> =
            Vec::with_capacity(projection.resource_names.len());
        for (canonical_name, resource_name) in projection.resource_names {
            resource_names.push((
                interner.intern(canonical_name),
                interner.intern(resource_name),
            ));
        }
        compact_projections.push((projection.projection_index, resource_names));
    }
    CompactProjectBatch {
        strings: interner.strings,
        facts,
        templates,
        analyses: compact_projections,
        unique_query_count,
        unique_projection_count,
    }
}

fn nullability_code(value: ProjectNullability) -> u8 {
    match value {
        ProjectNullability::Unknown => 0,
        ProjectNullability::NonNull => 1,
        ProjectNullability::Nullable => 2,
    }
}

fn transform_code(value: ProjectTransformKind) -> u8 {
    match value {
        ProjectTransformKind::Direct => 0,
        ProjectTransformKind::Cast => 1,
        ProjectTransformKind::Expression => 2,
        ProjectTransformKind::Aggregation => 3,
        ProjectTransformKind::Star => 4,
        ProjectTransformKind::Constant => 5,
    }
}

fn confidence_code(value: ProjectConfidence) -> u8 {
    match value {
        ProjectConfidence::Unknown => 0,
        ProjectConfidence::High => 1,
        ProjectConfidence::Medium => 2,
    }
}

fn project_analysis(inputs: ProjectAnalysisInputs<'_>) -> ProjectAnalysis {
    let cte_facts: CteColumnFacts = if inputs.recover_cte_facts {
        recovered_cte_facts(
            inputs.analysis,
            inputs.function_return_types,
            inputs.references,
        )
    } else {
        HashMap::new()
    };
    let infer_nullability = inputs.analysis.shape != QueryShape::SetOperation;
    let mut columns: Vec<ProjectColumn> = Vec::new();
    let mut lineage_columns: Vec<ProjectLineageColumn> = Vec::new();
    for projection in inputs
        .analysis
        .projections
        .iter()
        .filter(|projection| !projection.is_star)
    {
        let Some(output_column) = projection
            .name
            .as_ref()
            .filter(|name| !name.is_empty() && name.as_str() != SQL_WILDCARD)
        else {
            continue;
        };
        let (upstream_columns, confidence) =
            recovered_projection_lineage(projection, inputs.references, &cte_facts);
        let has_upstream = !upstream_columns.is_empty();
        let transform_kind = project_transform_kind(projection.transform_kind, has_upstream);
        columns.push(ProjectColumn {
            name: output_column.clone(),
            data_type: recovered_projection_type(
                projection,
                inputs.function_return_types,
                &cte_facts,
                true,
            ),
            nullability: if infer_nullability {
                recovered_projection_nullability(projection, &cte_facts)
            } else {
                ProjectNullability::Unknown
            },
        });
        lineage_columns.push(ProjectLineageColumn {
            output_column: output_column.clone(),
            upstream_columns,
            transform_kind,
            confidence: if matches!(transform_kind, ProjectTransformKind::Constant) || has_upstream
            {
                confidence
            } else {
                ProjectConfidence::Unknown
            },
        });
    }
    if !inputs.analysis.star_projections.is_empty() && inputs.references.len() == 1 {
        let order: HashMap<&str, usize> = inputs
            .declared_column_order
            .iter()
            .enumerate()
            .map(|(index, name)| (name.as_str(), index))
            .collect();
        let fallback = order.len();
        columns.sort_by_key(|column| order.get(column.name.as_str()).copied().unwrap_or(fallback));
        lineage_columns.sort_by_key(|column| {
            order
                .get(column.output_column.as_str())
                .copied()
                .unwrap_or(fallback)
        });
    }
    ProjectAnalysis {
        columns,
        lineage_columns,
        has_star: inputs.analysis.has_root_star,
    }
}

#[derive(Clone, Debug)]
struct CteColumnFact {
    data_type: Option<String>,
    nullability: ProjectNullability,
    upstream_columns: Vec<ProjectLineageSource>,
    confidence: ProjectConfidence,
}

type CteColumnFacts = HashMap<(String, String), CteColumnFact>;

fn recovered_cte_facts(
    analysis: &QueryAnalysis,
    function_return_types: &HashMap<String, String>,
    references: &HashMap<String, LineageResource>,
) -> CteColumnFacts {
    let mut facts: CteColumnFacts = HashMap::new();
    for cte in &analysis.cte_facts {
        for projection in &cte.projections {
            let Some(name) = projection.name.as_ref() else {
                continue;
            };
            let data_type =
                recovered_projection_type(projection, function_return_types, &facts, true);
            let nullability = if cte.shape == Some(QueryShape::SetOperation) {
                project_nullability(projection.nullability)
            } else {
                recovered_projection_nullability(projection, &facts)
            };
            let (upstream_columns, confidence) =
                recovered_projection_lineage(projection, references, &facts);
            facts.insert(
                (cte.name.to_lowercase(), name.to_lowercase()),
                CteColumnFact {
                    data_type,
                    nullability,
                    upstream_columns,
                    confidence,
                },
            );
        }
    }
    facts
}

fn recovered_projection_type(
    projection: &polyglot_sql::ProjectionFact,
    function_return_types: &HashMap<String, String>,
    cte_facts: &CteColumnFacts,
    allow_direct_type_hint: bool,
) -> Option<String> {
    if let Some(data_type) = projection.transform_function.as_ref().and_then(|function| {
        function_return_types
            .get(&function.name.to_uppercase())
            .cloned()
    }) {
        return Some(data_type);
    }
    if projection.transform_kind == TransformKind::Direct {
        if let Some(fact) = cte_column_fact(projection, cte_facts)
            && fact.data_type.is_some()
        {
            return fact.data_type.clone();
        }
        return allow_direct_type_hint
            .then(|| project_type(projection, function_return_types, false))
            .flatten();
    }
    project_type(projection, function_return_types, true)
}

fn recovered_projection_nullability(
    projection: &polyglot_sql::ProjectionFact,
    cte_facts: &CteColumnFacts,
) -> ProjectNullability {
    let direct = project_nullability(projection.nullability);
    if !matches!(direct, ProjectNullability::Unknown) {
        return direct;
    }
    if projection.transform_kind == TransformKind::Direct
        && let Some(fact) = cte_column_fact(projection, cte_facts)
    {
        return fact.nullability;
    }
    ProjectNullability::Unknown
}

fn cte_column_fact<'a>(
    projection: &polyglot_sql::ProjectionFact,
    cte_facts: &'a CteColumnFacts,
) -> Option<&'a CteColumnFact> {
    let source = projection.passthrough_source.as_ref()?;
    let column = projection.passthrough_column.as_ref()?;
    cte_facts.get(&(source.to_lowercase(), column.to_lowercase()))
}

fn recovered_projection_lineage(
    projection: &polyglot_sql::ProjectionFact,
    references: &HashMap<String, LineageResource>,
    cte_facts: &CteColumnFacts,
) -> (Vec<ProjectLineageSource>, ProjectConfidence) {
    if projection.transform_kind == TransformKind::Direct
        && let Some(fact) = cte_column_fact(projection, cte_facts)
    {
        return (fact.upstream_columns.clone(), fact.confidence);
    }
    project_upstream_columns(projection, references)
}

fn project_nullability(value: ProjectionNullability) -> ProjectNullability {
    match value {
        ProjectionNullability::NonNull => ProjectNullability::NonNull,
        ProjectionNullability::Nullable => ProjectNullability::Nullable,
        ProjectionNullability::Unknown => ProjectNullability::Unknown,
    }
}

fn project_type(
    projection: &polyglot_sql::ProjectionFact,
    function_return_types: &HashMap<String, String>,
    normalize_expression_type: bool,
) -> Option<String> {
    projection
        .cast_type
        .as_ref()
        .filter(|value| !value.is_empty() && value.as_str() != UNKNOWN_SQL_TYPE)
        .or_else(|| {
            projection
                .type_hint
                .as_ref()
                .filter(|value| !value.is_empty() && value.as_str() != UNKNOWN_SQL_TYPE)
        })
        .map(|value| {
            if normalize_expression_type {
                normalize_project_type(value)
            } else {
                value.to_string()
            }
        })
        .or_else(|| {
            projection.transform_function.as_ref().and_then(|function| {
                function_return_types
                    .get(&function.name.to_uppercase())
                    .cloned()
            })
        })
}

fn normalize_project_type(value: &str) -> String {
    let upper = value.to_uppercase();
    if upper == VARCHAR_SQL_TYPE {
        return "TEXT".to_string();
    }
    if let Some(length) = upper
        .strip_prefix("TEXT(")
        .and_then(|suffix| suffix.strip_suffix(')'))
    {
        return format!("VARCHAR({length})");
    }
    value.to_string()
}

fn project_upstream_columns(
    projection: &polyglot_sql::ProjectionFact,
    references: &HashMap<String, LineageResource>,
) -> (Vec<ProjectLineageSource>, ProjectConfidence) {
    let mut columns: Vec<ProjectLineageSource> = Vec::new();
    let mut seen: HashSet<(&str, &str, &str)> = HashSet::new();
    let mut confidence = ProjectConfidence::High;
    for upstream in &projection.upstream {
        if upstream.column.is_empty() || upstream.column == SQL_WILDCARD {
            continue;
        }
        let Some(source_name) = upstream
            .source_name
            .as_deref()
            .or(upstream.table.as_deref())
        else {
            confidence = ProjectConfidence::Unknown;
            continue;
        };
        let Some(resource) = references.get(source_name) else {
            continue;
        };
        if upstream.confidence != ReferenceConfidence::Resolved && upstream.source_alias.is_none() {
            confidence = ProjectConfidence::Medium;
        }
        let key = (
            resource.resource_type.as_str(),
            resource.resource_name.as_str(),
            upstream.column.as_str(),
        );
        if !seen.insert(key) {
            continue;
        }
        columns.push(ProjectLineageSource {
            resource_type: resource.resource_type.clone(),
            resource_name: resource.resource_name.clone(),
            column_name: upstream.column.clone(),
        });
    }
    columns.sort_by(|left, right| {
        (
            left.resource_type.as_str(),
            left.resource_name.as_str(),
            left.column_name.as_str(),
        )
            .cmp(&(
                right.resource_type.as_str(),
                right.resource_name.as_str(),
                right.column_name.as_str(),
            ))
    });
    (columns, confidence)
}

fn project_transform_kind(kind: TransformKind, has_upstream: bool) -> ProjectTransformKind {
    match kind {
        TransformKind::Star => ProjectTransformKind::Star,
        TransformKind::Cast => ProjectTransformKind::Cast,
        TransformKind::Aggregation => ProjectTransformKind::Aggregation,
        TransformKind::Constant => ProjectTransformKind::Constant,
        TransformKind::Direct => ProjectTransformKind::Direct,
        TransformKind::Expression if !has_upstream => ProjectTransformKind::Constant,
        TransformKind::Expression => ProjectTransformKind::Expression,
    }
}
