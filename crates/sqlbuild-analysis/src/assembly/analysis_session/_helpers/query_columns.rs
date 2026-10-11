//! Python's per-query column analysis outside the session, behind its entry point.

use std::collections::HashMap;

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;
use sqlbuild_sqltext::compiler::main::placeholder_defaults::placeholder_defaults;

use crate::assembly::analysis_session::_helpers::catalog_state::SessionCatalog;
use crate::assembly::analysis_session::_helpers::compact_batch::{
    Batch, BatchMember, MemberAnalysis, MemberResult,
};
use crate::assembly::analysis_session::_helpers::cte_facts::{
    LegacyAnalysis, LegacyInput, RecoveryProfile, legacy_analysis,
};
use crate::assembly::analysis_session::_helpers::enrichment::{
    Enrichment, EnrichmentInput, enrichment,
};
use crate::assembly::analysis_session::_helpers::mappings::ShapeTable;
use crate::assembly::analysis_session::models::{
    ModelReference, ModelRequest, QueryColumns, QueryColumnsInput, QueryColumnsMode,
    QueryColumnsRequest,
};
use crate::semantic_validation::main::normalize::normalize_analysis_sql;
use crate::semantic_validation::models::{NormalizationInput, ProjectCatalog};

/// The request with `Parse` and `Legacy` SQL normalized in order; Err is the first rejection.
pub(crate) fn normalized_request(
    request: &QueryColumnsRequest,
) -> Result<QueryColumnsRequest, String> {
    let mut normalized: QueryColumnsRequest = request.clone();
    for query in &mut normalized.queries {
        if matches!(
            query.mode,
            QueryColumnsMode::Parse | QueryColumnsMode::Legacy
        ) {
            query.sql = normalize_analysis_sql(NormalizationInput {
                sql: std::mem::take(&mut query.sql),
                dialect: request.normalization_dialect.clone(),
                stubs: HashMap::new(),
                placeholders: HashMap::new(),
            })?;
        }
    }
    Ok(normalized)
}

/// Each query's columns, in order; only `Batch` queries read the catalog.
pub(crate) fn query_columns(
    catalog: Option<&ProjectCatalog>,
    request: &QueryColumnsRequest,
) -> Result<Vec<QueryColumns>, String> {
    let types: ShapeTable = ShapeTable::from_shapes(&request.types);
    let nullability: ShapeTable = ShapeTable::from_shapes(&request.nullability);
    let analysed: Vec<(usize, &QueryColumnsInput)> = request
        .queries
        .iter()
        .enumerate()
        .filter(|(_, query)| query.mode == QueryColumnsMode::Batch)
        .collect();
    let mut batch_results: HashMap<usize, MemberResult> = HashMap::new();
    if !analysed.is_empty() {
        let catalog: &ProjectCatalog =
            catalog.ok_or("a compact query batch without an analysis catalog")?;
        let mut session_catalog: SessionCatalog = SessionCatalog::new(catalog, &Vec::new());
        let batch = Batch {
            dialect: &request.dialect,
            function_return_types: &request.function_return_types,
            rich_type_inference: true,
            members: analysed
                .iter()
                .map(|(_, query)| BatchMember {
                    query_sql: &query.sql,
                    placeholders: &query.placeholders,
                    analysis_names: query.analysis_names.iter().map(String::as_str).collect(),
                    lineage_references: &query.lineage_references,
                    recover_cte_facts: query.recover_cte_facts,
                    binding_schema: None,
                })
                .collect(),
            types: &types,
            nullability: &nullability,
        };
        let results: Vec<MemberResult> = session_catalog.analyze_batch(&batch)?;
        batch_results.extend(analysed.iter().map(|(index, _)| *index).zip(results));
    }
    let tables = Tables {
        request,
        types: &types,
        nullability: &nullability,
    };
    request
        .queries
        .iter()
        .enumerate()
        .map(|(index, query)| match batch_results.remove(&index) {
            None if query.mode == QueryColumnsMode::Reanalysis => tables.reanalysed(query),
            None => tables.parsed(
                query,
                &parse_cleaned_sql(query),
                query.mode == QueryColumnsMode::Parse,
            ),
            Some(result) => match result.analysis {
                MemberAnalysis::Projected {
                    columns, has_star, ..
                } => Ok(QueryColumns {
                    succeeded: true,
                    columns: Some(columns),
                    has_star,
                }),
                MemberAnalysis::Legacy { .. } => tables.parsed(query, &result.cleaned_sql, false),
                MemberAnalysis::Failed => Ok(QueryColumns::default()),
            },
        })
        .collect()
}

/// Python's `substitute_placeholder_defaults` over SQL its caller already normalized.
fn parse_cleaned_sql(query: &QueryColumnsInput) -> String {
    if query.placeholders.is_empty() {
        query.sql.clone()
    } else {
        placeholder_defaults(&query.sql, &query.placeholders)
    }
}

struct Tables<'a> {
    request: &'a QueryColumnsRequest,
    types: &'a ShapeTable,
    nullability: &'a ShapeTable,
}

impl Tables<'_> {
    /// Python's `analyze_columns_and_lineage_with_polyglot` without a precomputed analysis.
    fn reanalysed(&self, query: &QueryColumnsInput) -> Result<QueryColumns, String> {
        let model = ModelRequest {
            query_sql: query.sql.clone(),
            placeholders: query.placeholders.clone(),
            references: query
                .analysis_names
                .iter()
                .map(|analysis_name| ModelReference {
                    analysis_name: analysis_name.clone(),
                    model_ref: false,
                })
                .collect(),
            lineage_references: query.lineage_references.clone(),
            recover_cte_facts: query.recover_cte_facts,
            ..ModelRequest::default()
        };
        let enriched: Enrichment = enrichment(&EnrichmentInput {
            model: &model,
            input_schemas: &self.request.types,
            dialect: &self.request.dialect,
            function_return_types: &self.request.function_return_types,
            nullability_rules: self.request.nullability_rules.as_ref(),
            nullability_callback: self.request.nullability_callback.as_ref(),
        })?;
        Ok(QueryColumns {
            succeeded: enriched.analysis_succeeded,
            columns: enriched.columns,
            has_star: enriched.has_star,
        })
    }

    /// Python's analysis of the parsed tree.
    fn parsed(
        &self,
        query: &QueryColumnsInput,
        cleaned_sql: &str,
        full_nullability: bool,
    ) -> Result<QueryColumns, String> {
        let analysis: LegacyAnalysis = catch_compiler_panic(|| {
            legacy_analysis(&LegacyInput {
                cleaned_sql,
                lineage_references: &query.lineage_references,
                recover: query.recover_cte_facts,
                full_nullability,
                types: self.types,
                nullability: self.nullability,
                profile: RecoveryProfile {
                    dialect: &self.request.dialect,
                    function_return_types: &self.request.function_return_types,
                    rules: self.request.nullability_rules.as_ref(),
                    callback: self.request.nullability_callback.as_ref(),
                },
            })
        })?;
        Ok(QueryColumns {
            succeeded: analysis.succeeded,
            columns: analysis.columns,
            has_star: analysis.has_star,
        })
    }
}
