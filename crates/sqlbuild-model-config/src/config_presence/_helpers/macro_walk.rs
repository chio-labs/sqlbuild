//! The walk `validate_no_macros_in_config_value` makes over nested config values.

use crate::config_presence::_helpers::macro_calls::macro_call;
use crate::config_presence::models::MacroPath;
use crate::types::{AuthoredNode, NodeKind};

fn walk<N: AuthoredNode>(node: &N, path: &[String]) -> MacroPath {
    match node.kind() {
        NodeKind::Str if node.with_text(macro_call).unwrap_or(false) => {
            MacroPath::Found(path.to_vec())
        }
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

/// The first macro path among `entries`, string keys only, each below `path`.
pub(crate) fn walk_entries<N: AuthoredNode>(entries: &[(N, N)], path: &[String]) -> MacroPath {
    for (key, value) in entries {
        if key.kind() != NodeKind::Str {
            continue;
        }
        let Some(name) = key.text() else {
            continue;
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
