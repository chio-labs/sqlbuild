//! The companion resources and single-resource problems of singular audits.

use std::collections::BTreeSet;

use crate::audits::constants::{
    FUNCTION_RESOURCE, SEED_KIND, SEED_RESOURCE, SOURCE_KIND, SOURCE_RESOURCE, TABLE_FUNCTION_KIND,
};

/// The resource kind a non-model reference kind names, if it counts as a companion.
pub(crate) fn companion_resource(kind: &str) -> Option<&'static str> {
    match kind {
        SOURCE_KIND => Some(SOURCE_RESOURCE),
        SEED_KIND => Some(SEED_RESOURCE),
        TABLE_FUNCTION_KIND => Some(FUNCTION_RESOURCE),
        _ => None,
    }
}

/// `_single_resource_problem`: the message and help for an audit that is not cross-resource.
pub(crate) fn single_resource_problem(
    models: &BTreeSet<&str>,
    has_companions: bool,
) -> (String, String) {
    if let (1, Some(model)) = (models.len(), models.iter().next()) {
        return (
            format!("checks only model '{model}'; singular audits must be cross-resource"),
            format!(
                "attach a generic audit to '{model}' instead: write it in an audits/generic/ \
                 role and select FROM @relation, joining @relation to itself for self-join checks"
            ),
        );
    }
    if has_companions {
        return (
            "checks only sources or seeds; singular audits must reference at least one model"
                .to_owned(),
            "attach YAML audits to the source or seed instead".to_owned(),
        );
    }
    (
        "references no SQLBuild resource; singular audits must reference two or more models, or \
         a model plus a source, seed, or table function via __ref(), __source(), or __seed()"
            .to_owned(),
        "reference resources through SQLBuild calls instead of hard-coded relation names, or \
         attach a generic audit to the resource being checked"
            .to_owned(),
    )
}
