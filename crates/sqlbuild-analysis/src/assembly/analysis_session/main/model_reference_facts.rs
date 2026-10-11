//! A model's analysis references, lineage reference map and required relation names.

use std::collections::BTreeSet;

use crate::assembly::analysis_session::constants::{
    LINEAGE_RESOURCE_TYPES, REF_KIND, TABLE_FUNCTION_ANALYSIS_PREFIX, TABLE_FUNCTION_KIND, UDF_KIND,
};
use crate::assembly::analysis_session::models::{ModelReference, ModelReferenceFacts};

/// The reference facts of `(kind, name)` rows, as Python's model analysis rows derive them.
pub fn model_reference_facts(rows: &[(String, String)]) -> ModelReferenceFacts {
    let mut facts = ModelReferenceFacts::default();
    let mut required: BTreeSet<String> = BTreeSet::new();
    for (kind, name) in rows {
        let analysis_name = if kind == TABLE_FUNCTION_KIND {
            format!("{TABLE_FUNCTION_ANALYSIS_PREFIX}{name}")
        } else {
            name.clone()
        };
        facts.references.push(ModelReference {
            analysis_name: analysis_name.clone(),
            model_ref: kind == REF_KIND,
        });
        if let Some((_, resource_type)) = LINEAGE_RESOURCE_TYPES
            .iter()
            .find(|(lineage_kind, _)| lineage_kind == kind)
        {
            let entry = (
                analysis_name.clone(),
                (*resource_type).to_owned(),
                name.clone(),
            );
            match facts
                .lineage_references
                .iter_mut()
                .find(|(existing, _, _)| *existing == analysis_name)
            {
                Some(existing) => *existing = entry,
                None => facts.lineage_references.push(entry),
            }
        }
        if kind != UDF_KIND {
            required.insert(analysis_name);
        }
    }
    facts.required_names = required.into_iter().collect();
    facts
}
