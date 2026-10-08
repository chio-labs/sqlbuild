//! The first config field, in Python's walk order, whose string holds a macro call.

use crate::config_presence::_helpers::macro_calls::macro_call;
use crate::config_presence::models::{MacroPath, Presence};
use crate::types::{AuthoredNode, NodeKind};

/// Walk config values as `validate_no_macros_in_config_value` does, skipping the `skipped` keys.
pub fn first_macro_path<N: AuthoredNode>(values: &N, skipped: &[&str]) -> MacroPath {
    let mut entries = values.entries();
    entries.retain(|(key, _)| !skipped.iter().any(|name| key.is_text(name)));
    walk_entries(&entries, &[])
}

fn walk<N: AuthoredNode>(node: &N, path: &[String]) -> MacroPath {
    match node.kind() {
        NodeKind::Str => match node.with_text(macro_call) {
            Some(Presence::Present) => MacroPath::Found(path.to_vec()),
            Some(Presence::Absent) => MacroPath::Absent,
            Some(Presence::Deferred) | None => MacroPath::Deferred,
        },
        NodeKind::Map => walk_entries(&node.entries(), path),
        NodeKind::List | NodeKind::Tuple => {
            for item in node.items() {
                let found = walk(&item, path);
                if found != MacroPath::Absent {
                    return found;
                }
            }
            MacroPath::Absent
        }
        _ => MacroPath::Absent,
    }
}

fn walk_entries<N: AuthoredNode>(entries: &[(N, N)], path: &[String]) -> MacroPath {
    for (key, value) in entries {
        if key.kind() != NodeKind::Str {
            continue;
        }
        let Some(name) = key.text() else {
            return MacroPath::Deferred;
        };
        let mut child: Vec<String> = path.to_vec();
        child.push(name);
        let found = walk(value, &child);
        if found != MacroPath::Absent {
            return found;
        }
    }
    MacroPath::Absent
}
