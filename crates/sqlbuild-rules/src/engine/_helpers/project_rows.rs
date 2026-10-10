//! Rules model rows read from the compile's natively owned project facts.

use sqlbuild_analysis::compiled_project::models::{
    CompiledModelFacts, DeclarationFact, ModelSchemaFact,
};

use crate::models::{
    Declaration, DeclarationMember, DynamicFamilyRow, DynamicProofRow, ModelRow, Reference,
    SchemaColumnRow, SchemaRow,
};

/// The row the rules builder reads for one model; the authored query wins over the whole file.
pub(crate) fn model_row(facts: &CompiledModelFacts) -> Result<ModelRow, String> {
    if let Some(error) = &facts.config.encoding_error {
        return Err(error.clone());
    }
    let analysis = facts.analysis.clone().unwrap_or_default();
    Ok(ModelRow {
        name: facts.name.clone(),
        relative_path: facts.relative_path.clone(),
        query_sql: facts.query_sql.clone(),
        authored_sql: if facts.authored_query_sql.is_empty() {
            facts.authored_sql.clone()
        } else {
            facts.authored_query_sql.clone()
        },
        config: facts.config.values.clone(),
        authored_config_keys: facts.config.header_keys.clone(),
        logical_schema: facts.config.layer_schema.clone(),
        references: facts
            .references
            .iter()
            .map(|reference| Reference {
                ref_kind: reference.kind.clone(),
                ref_name: reference.name.clone(),
                ref_package: reference.package.clone(),
            })
            .collect(),
        schema: facts.schema.as_ref().map(schema_row),
        inferred_columns: analysis.inferred_columns,
        dynamic_proof: analysis.dynamic_proof.map(|proof| DynamicProofRow {
            output_proven: proof.output_proven,
            bare_dynamic_pivot: proof.bare_dynamic_pivot,
            families: proof.families,
        }),
        enum_columns: facts.enum_columns.clone(),
        enum_declarations: facts.enum_declarations.iter().map(declaration).collect(),
        constant_declarations: facts
            .constant_declarations
            .iter()
            .map(declaration)
            .collect(),
    })
}

fn schema_row(schema: &ModelSchemaFact) -> SchemaRow {
    SchemaRow {
        audit_count: schema.audit_count,
        columns: schema
            .columns
            .iter()
            .map(|column| SchemaColumnRow {
                name: column.name.clone(),
                data_type: column.data_type.clone(),
                nullable: column.nullable,
                audit_count: column.audit_count,
            })
            .collect(),
        dynamic_columns: schema
            .dynamic_columns
            .iter()
            .map(|family| DynamicFamilyRow {
                key: family.key.clone(),
                name: family.name.clone(),
                pivot_column: family.pivot_column.clone(),
                value_column: family.value_column.clone(),
                aggregate: family.aggregate.clone(),
                data_type: family.data_type.clone(),
                name_pattern: family.name_pattern.clone(),
            })
            .collect(),
    }
}

/// A declaration as the rules request carries it.
pub(crate) fn declaration(fact: &DeclarationFact) -> Declaration {
    Declaration {
        name: fact.name.clone(),
        relative_path: fact.relative_path.clone(),
        members: fact
            .members
            .iter()
            .map(|(name, value)| DeclarationMember {
                name: name.clone(),
                value: value.clone(),
            })
            .collect(),
        value: fact.value.clone(),
        value_type: fact.value_type.clone(),
        render_as: fact.render_as.clone(),
    }
}
