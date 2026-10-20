//! One cached declaration's report values.

use crate::scope_cache::models::CachedDeclaration;
use crate::scope_report::models::{ConstantValues, DeclarationValues, EnumValues, MacroValues};

/// One declaration's report values.
#[must_use]
pub fn cached_declaration_values(item: &CachedDeclaration) -> DeclarationValues {
    DeclarationValues {
        macro_values: item.macro_facts.as_ref().map(|facts| MacroValues {
            parameters: facts.parameters.clone(),
            dependencies: facts.dependencies.clone(),
            source_digest: facts.source_digest.clone(),
        }),
        enum_values: item.enum_facts.as_ref().map(|facts| EnumValues {
            members: facts.members.clone(),
            scalar_type: facts.scalar_type.clone(),
        }),
        constant_values: item.constant_facts.as_ref().map(|facts| ConstantValues {
            logical_type: facts.logical_type.clone(),
            collection_kind: facts.collection_kind.clone(),
            item_count: facts.item_count,
            nullable: facts.nullable,
            render_as: facts.render_as.clone(),
        }),
    }
}
