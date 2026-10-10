//! Python's hook-read validation: unknown reads raise, reads of a hook's own dependant are P007.

use std::collections::HashSet;

use crate::explicit_references::_helpers::audit_gates::GateEdge;
use crate::explicit_references::_helpers::graph::{Upstream, lineage_upstream, reaches};
use crate::explicit_references::constants::{
    HOOK_READ_CODE, MODEL_TYPE, PYTHON_DESTINATION, SEED_TYPE, SOURCE_TYPE, SQL_DESTINATION,
};
use crate::explicit_references::models::{PythonHook, ReferenceDiagnostic, ReferenceRequest};
use crate::explicit_references::types::ResourceKey;

/// How diagnostics name a hook.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum HookType {
    Python,
    Sql,
    InlineSql,
}

/// One ordering edge: model `gated` waits for `read`, which one of its hooks reads.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct HookEdge {
    hook_name: String,
    gated: ResourceKey,
    read: ResourceKey,
    hook_type: HookType,
    path: Option<String>,
}

/// The `CompileInputError` message for the first unknown read, hooks taken by name.
pub(crate) fn unknown_read(request: &ReferenceRequest) -> Option<String> {
    let mut hooks: Vec<&PythonHook> = request.hooks.iter().collect();
    hooks.sort_by(|left, right| left.name.cmp(&right.name));
    for hook in hooks {
        for (kind, name) in &hook.reads {
            if !known(request, kind, name) {
                return Some(format!(
                    "Python hook '{}' in '{}' reads unknown {kind} '{name}'",
                    hook.name, hook.path
                ));
            }
        }
    }
    None
}

/// Whether a model, source or seed of that kind and name exists.
fn known(request: &ReferenceRequest, kind: &str, name: &str) -> bool {
    [MODEL_TYPE, SOURCE_TYPE, SEED_TYPE].contains(&kind)
        && request
            .resources
            .iter()
            .any(|resource| resource.key.0 == kind && resource.key.1 == name)
}

/// `hook_read_cycles_impl` as Python's P007 diagnostics, in its order.
pub(crate) fn hook_diagnostics(
    request: &ReferenceRequest,
    gates: &[GateEdge],
) -> Vec<ReferenceDiagnostic> {
    let mut edges: Vec<HookEdge> = hook_edges(request);
    if edges.is_empty() {
        return Vec::new();
    }
    let mut upstream: Upstream = lineage_upstream(&request.resources);
    for gate in gates {
        upstream
            .entry(gate.gated.clone())
            .or_default()
            .push(gate.read.clone());
    }
    for edge in &edges {
        upstream
            .entry(edge.gated.clone())
            .or_default()
            .push(edge.read.clone());
    }
    edges.sort_by(|left, right| {
        (&left.gated.1, &left.hook_name, &left.read.1).cmp(&(
            &right.gated.1,
            &right.hook_name,
            &right.read.1,
        ))
    });
    edges
        .iter()
        .filter(|edge| reaches(&upstream, &edge.read, &edge.gated))
        .map(diagnostic)
        .collect()
}

/// `hook_read_edges_impl`: Python then SQL hook reads per model, deduplicated, minus self-reads.
fn hook_edges(request: &ReferenceRequest) -> Vec<HookEdge> {
    let mut candidates: Vec<HookEdge> = Vec::new();
    for model in &request.models {
        let gated: ResourceKey = (MODEL_TYPE.to_owned(), model.name.clone());
        for hook_name in &model.python_hooks {
            let reads: &[ResourceKey] = request
                .hooks
                .iter()
                .rev()
                .find(|hook| &hook.name == hook_name && !hook.reads.is_empty())
                .map_or(&[], |hook| hook.reads.as_slice());
            let path: Option<String> = request
                .hooks
                .iter()
                .rev()
                .find(|hook| &hook.name == hook_name)
                .map(|hook| hook.path.clone());
            candidates.extend(reads.iter().map(|read| HookEdge {
                hook_name: hook_name.clone(),
                gated: gated.clone(),
                read: read.clone(),
                hook_type: HookType::Python,
                path: path.clone(),
            }));
        }
        for hook in &model.sql_hooks {
            let (hook_name, hook_type) = match &hook.name {
                Some(name) => (name.clone(), HookType::Sql),
                None => (
                    format!("{}[{}]", hook.hook_key, hook.index),
                    HookType::InlineSql,
                ),
            };
            let path: String = hook.path.clone().unwrap_or_else(|| model.path.clone());
            candidates.extend(hook.reads.iter().map(|read| HookEdge {
                hook_name: hook_name.clone(),
                gated: gated.clone(),
                read: read.clone(),
                hook_type,
                path: Some(path.clone()),
            }));
        }
    }
    let mut seen: HashSet<HookEdge> = HashSet::new();
    candidates
        .into_iter()
        .filter(|edge| edge.read != edge.gated && seen.insert(edge.clone()))
        .collect()
}

fn diagnostic(edge: &HookEdge) -> ReferenceDiagnostic {
    let label: String = match edge.hook_type {
        HookType::Python => format!("Python hook '{}'", edge.hook_name),
        HookType::Sql => format!("SQL hook '{}'", edge.hook_name),
        HookType::InlineSql => format!("inline SQL hook {}", edge.hook_name),
    };
    let destination: &str = if edge.hook_type == HookType::Python {
        PYTHON_DESTINATION
    } else {
        SQL_DESTINATION
    };
    let gated: &str = &edge.gated.1;
    ReferenceDiagnostic {
        code: HOOK_READ_CODE,
        message: format!(
            "{label} on {} '{gated}' reads {} '{}', which depends on '{gated}'; a hook runs as \
             part of its model, so it cannot wait for a resource built from that model",
            edge.gated.0, edge.read.0, edge.read.1
        ),
        help: format!(
            "attach the hook to a model built after '{}', or drop the read and use \
             {destination} for '{gated}' itself",
            edge.read.1
        ),
        path: edge.path.clone(),
        owner: None,
        line: None,
        resource: Some(edge.gated.clone()),
    }
}
