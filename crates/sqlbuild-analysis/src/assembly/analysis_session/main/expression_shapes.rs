//! Python's `get_expression_source_shapes` for expressions its catalog has not inferred.

use crate::assembly::analysis_session::_helpers::catalog_state::SessionCatalog;
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::assembly::analysis_session::_helpers::compact_batch::{
    Batch, BatchMember, MemberAnalysis, MemberResult,
};
use crate::assembly::analysis_session::_helpers::cte_facts::{
    LegacyAnalysis, LegacyInput, RecoveryProfile, legacy_analysis,
};
use crate::assembly::analysis_session::_helpers::mappings::ShapeTable;
use crate::assembly::analysis_session::_helpers::publication::{ShapeOptions, ShapeSource};
use crate::assembly::analysis_session::_helpers::session::shape_columns;
use crate::assembly::analysis_session::models::{ExpressionShape, ExpressionShapeRequest};
use crate::assembly::analysis_session::types::{Pairs, Shapes};
use crate::semantic_validation::models::ProjectCatalog;

/// One shape per expression, in order; an error is the one Python raises.
pub fn expression_shapes(
    catalog: &ProjectCatalog,
    request: &ExpressionShapeRequest,
) -> Result<Vec<ExpressionShape>, String> {
    let mut session_catalog: SessionCatalog = SessionCatalog::new(catalog, &Vec::new());
    let no_placeholders: Pairs = Vec::new();
    let empty: ShapeTable = ShapeTable::default();
    let batch = Batch {
        dialect: &request.dialect,
        function_return_types: &request.function_return_types,
        rich_type_inference: true,
        members: request
            .expressions
            .iter()
            .map(|expression| BatchMember {
                query_sql: expression,
                placeholders: &no_placeholders,
                analysis_names: Vec::new(),
                lineage_references: &[],
                recover_cte_facts: true,
                binding_schema: None,
            })
            .collect(),
        types: &empty,
        nullability: &empty,
    };
    let results: Vec<MemberResult> = session_catalog.analyze_batch(&batch)?;
    let options = ShapeOptions {
        dialect: &request.dialect,
        case_sensitive: request.case_sensitive_shapes,
    };
    let no_inputs: Shapes = Vec::new();
    let mut shapes: Vec<ExpressionShape> = Vec::with_capacity(results.len());
    for (expression, result) in request.expressions.iter().zip(results) {
        shapes.push(match result.analysis {
            MemberAnalysis::Legacy { .. } => {
                let legacy: LegacyAnalysis = catch_compiler_panic(|| {
                    legacy_analysis(&LegacyInput {
                        cleaned_sql: &result.cleaned_sql,
                        lineage_references: &[],
                        recover: true,
                        full_nullability: false,
                        types: &empty,
                        nullability: &empty,
                        profile: RecoveryProfile {
                            dialect: &request.dialect,
                            function_return_types: &request.function_return_types,
                            rules: request.nullability_rules.as_ref(),
                            callback: request.nullability_callback.as_ref(),
                        },
                    })
                })?;
                match legacy.columns {
                    Some(columns) if !columns.is_empty() && !legacy.has_star => {
                        ExpressionShape::Inferred(session_catalog.inferred_binding_shape(
                            &options,
                            ShapeSource {
                                sql: expression,
                                columns: shape_columns(&columns),
                                inputs: &no_inputs,
                                snapshot_columns: None,
                            },
                        )?)
                    }
                    _ => ExpressionShape::Absent,
                }
            }
            MemberAnalysis::Projected {
                columns, has_star, ..
            } if !columns.is_empty() && !has_star => {
                ExpressionShape::Inferred(session_catalog.inferred_binding_shape(
                    &options,
                    ShapeSource {
                        sql: expression,
                        columns: shape_columns(&columns),
                        inputs: &no_inputs,
                        snapshot_columns: None,
                    },
                )?)
            }
            MemberAnalysis::Projected { .. } | MemberAnalysis::Failed => ExpressionShape::Absent,
        });
    }
    Ok(shapes)
}
