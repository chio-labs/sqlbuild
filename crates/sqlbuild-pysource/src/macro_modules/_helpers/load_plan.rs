//! The synthetic package name, parent packages and dependency-first order of macro modules.

use std::cmp::Reverse;
use std::collections::{BTreeSet, BinaryHeap, HashMap};

use sha2::{Digest, Sha256};

use crate::macro_modules::constants::{SYNTHETIC_DIGEST_LENGTH, SYNTHETIC_PACKAGE_PREFIX};
use crate::macro_modules::models::MacroModuleSpec;

/// The root package named by a digest of every module's name, path and contents.
pub(crate) fn synthetic_root(modules: &[MacroModuleSpec]) -> String {
    let mut by_name: Vec<&MacroModuleSpec> = modules.iter().collect();
    by_name.sort_by(|left, right| left.name.cmp(&right.name));
    let joined: String = by_name
        .iter()
        .map(|module| format!("{}\0{}\0{}", module.name, module.file_path, module.contents))
        .collect::<Vec<String>>()
        .join("\0");
    let digest: String = format!("{:x}", Sha256::digest(joined.as_bytes()));
    format!(
        "{SYNTHETIC_PACKAGE_PREFIX}{}",
        &digest[..SYNTHETIC_DIGEST_LENGTH]
    )
}

/// The root and every parent package of a module, shallowest first.
pub(crate) fn parent_packages(root: &str, modules: &[MacroModuleSpec]) -> Vec<String> {
    let mut packages: BTreeSet<(usize, String)> = BTreeSet::from([(0, root.to_owned())]);
    for module in modules {
        let parts: Vec<&str> = module.name.split('.').collect();
        for index in 1..parts.len() {
            let package: String = format!("{root}.{}", parts[..index].join("."));
            packages.insert((package.matches('.').count(), package));
        }
    }
    packages.into_iter().map(|(_, package)| package).collect()
}

/// Kahn order over module dependencies, taking the smallest ready name first.
pub(crate) fn load_order(modules: &[MacroModuleSpec]) -> Vec<String> {
    let mut remaining: HashMap<&str, usize> = HashMap::new();
    let mut dependents: HashMap<&str, Vec<&str>> = HashMap::new();
    for module in modules {
        remaining.insert(&module.name, module.dependencies.len());
        for dependency in &module.dependencies {
            dependents
                .entry(dependency.as_str())
                .or_default()
                .push(&module.name);
        }
    }
    let mut ready: BinaryHeap<Reverse<&str>> = remaining
        .iter()
        .filter(|(_, count)| **count == 0)
        .map(|(name, _)| Reverse(*name))
        .collect();
    let mut order: Vec<String> = Vec::new();
    while let Some(Reverse(name)) = ready.pop() {
        order.push(name.to_owned());
        for dependent in dependents.get(name).into_iter().flatten() {
            if let Some(count) = remaining.get_mut(dependent) {
                *count -= 1;
                if *count == 0 {
                    ready.push(Reverse(dependent));
                }
            }
        }
    }
    order
}
