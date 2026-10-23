//! Rewrite the Python imports of modules that move, or say why one cannot be rewritten.

use crate::import_rewrites::_helpers::import_statements::source_rewrites;
use crate::import_rewrites::_helpers::module_paths::module_parts;
use crate::import_rewrites::_helpers::package_bindings::package_bindings;
use crate::import_rewrites::constants::STAR_IMPORT_NAME;
use crate::import_rewrites::models::{ImportRewrites, ModuleMove, PythonSource};
use crate::import_rewrites::types::ModuleMoves;

/// Byte-offset import edits `moves` need in every source, and the imports they cannot rewrite.
#[must_use]
pub fn python_import_rewrites(sources: &[PythonSource], moves: &[ModuleMove]) -> ImportRewrites {
    let modules: ModuleMoves = moves
        .iter()
        .filter_map(|item| Some((module_parts(&item.from)?, module_parts(&item.to)?)))
        .filter(|(old, new)| old != new)
        .collect();
    let mut rewrites = ImportRewrites::default();
    if modules.is_empty() {
        return rewrites;
    }
    let bindings = package_bindings(sources);
    let names: Vec<&str> = modules
        .keys()
        .filter_map(|old| old.last().map(String::as_str))
        .collect();
    let mut ordered: Vec<&PythonSource> = sources.iter().collect();
    ordered.sort_by(|left, right| left.path.cmp(&right.path));
    for source in ordered {
        let destination: Option<&str> = moves
            .iter()
            .find(|item| item.from == source.path)
            .map(|item| item.to.as_str());
        let mentions: bool = names.iter().any(|name| source.contents.contains(name))
            || source.contents.contains(STAR_IMPORT_NAME);
        if destination.is_none() && !mentions {
            continue;
        }
        let (edits, refusals) = source_rewrites(source, destination, (&modules, &bindings));
        rewrites.edits.extend(edits);
        rewrites.refusals.extend(refusals);
    }
    rewrites
}
