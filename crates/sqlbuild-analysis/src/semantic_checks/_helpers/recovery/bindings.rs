//! Python's `update_binding_models`: model binding facts among project diagnostics.

use std::collections::{HashMap, HashSet};

/// One diagnostic as `update_binding_models` reads it: code, whether it is a model's, and name.
pub(crate) struct BindingOwner<'a> {
    pub(crate) code: &'a str,
    pub(crate) is_model: bool,
    pub(crate) resource_name: Option<&'a str>,
}

/// Positions in `diagnostics` of each model's diagnostics whose codes it already binds.
pub(crate) fn binding_positions(
    models: &[(&str, HashSet<&str>)],
    diagnostics: &[BindingOwner<'_>],
) -> Vec<Vec<usize>> {
    let mut by_model: HashMap<&str, Vec<usize>> = HashMap::new();
    for (position, diagnostic) in diagnostics.iter().enumerate() {
        if diagnostic.is_model {
            by_model
                .entry(diagnostic.resource_name.unwrap_or(""))
                .or_default()
                .push(position);
        }
    }
    let mut result: Vec<Vec<usize>> = Vec::with_capacity(models.len());
    for (name, codes) in models {
        let mut kept: Vec<usize> = Vec::new();
        for position in by_model.get(name).map_or(&[][..], Vec::as_slice) {
            if codes.contains(diagnostics[*position].code) {
                kept.push(*position);
            }
        }
        result.push(kept);
    }
    result
}
