//! Python's attached-audit gate edges and the P005 cycles they close.

use std::collections::{HashMap, HashSet};

use crate::explicit_references::_helpers::graph::{Upstream, lineage_upstream, reaches};
use crate::explicit_references::constants::{
    AUDIT_GATE_CODE, MODEL_TYPE, READABLE_TYPES, SEED_TYPE, SOURCE_TYPE, TABLE_FUNCTION_TYPE,
    UDF_TYPE,
};
use crate::explicit_references::models::{AuditGate, ReferenceDiagnostic, ReferenceRequest};
use crate::explicit_references::types::ResourceKey;

/// One ordering edge: `gated` waits for `read`, which an audit on `target` reads.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub(crate) struct GateEdge {
    pub(crate) gated: ResourceKey,
    pub(crate) read: ResourceKey,
}

/// An audit's target and the other resources it reads.
struct Gate<'a> {
    target: &'a ResourceKey,
    reads: Vec<&'a ResourceKey>,
}

/// `attached_audit_gate_edges_impl`: edges to a fixed point, as sources gain triggering models.
pub(crate) fn gate_edges(request: &ReferenceRequest) -> Vec<GateEdge> {
    let mut triggers: HashMap<ResourceKey, HashSet<ResourceKey>> = HashMap::new();
    for resource in request
        .resources
        .iter()
        .filter(|item| item.key.0 == MODEL_TYPE)
    {
        for dep in resource.deps.iter().filter(|dep| dep.0 == SOURCE_TYPE) {
            triggers
                .entry(dep.clone())
                .or_default()
                .insert(resource.key.clone());
        }
    }
    let gates: Vec<Gate<'_>> = request.audits.iter().filter_map(gate).collect();
    let mut edges: Vec<GateEdge> = Vec::new();
    let mut seen: HashSet<GateEdge> = HashSet::new();
    let mut changed = true;
    while changed {
        changed = false;
        for gate in &gates {
            for edge in edges_of(gate, &triggers) {
                if !seen.insert(edge.clone()) {
                    continue;
                }
                changed = true;
                if edge.read.0 == SOURCE_TYPE && edge.gated.0 == MODEL_TYPE {
                    triggers
                        .entry(edge.read.clone())
                        .or_default()
                        .insert(edge.gated.clone());
                }
                edges.push(edge);
            }
        }
    }
    edges
}

/// `attached_audit_gate_cycles_impl` as Python's P005 diagnostics, in its order.
pub(crate) fn gate_diagnostics(
    request: &ReferenceRequest,
    edges: &[GateEdge],
) -> Vec<ReferenceDiagnostic> {
    let mut upstream: Upstream = lineage_upstream(&request.resources);
    for edge in edges {
        upstream
            .entry(edge.gated.clone())
            .or_default()
            .push(edge.read.clone());
    }
    let mut audits: Vec<&AuditGate> = request.audits.iter().collect();
    audits.sort_by(|left, right| left.name.cmp(&right.name));
    let mut cycles: Vec<(&AuditGate, &ResourceKey, &ResourceKey)> = Vec::new();
    for audit in audits {
        let Some(target) = &audit.target else {
            continue;
        };
        for read in extra_reads(audit, target) {
            let cycle = (audit, target, read);
            if reaches(&upstream, read, target)
                && !cycles
                    .iter()
                    .any(|(other, t, r)| other.name == audit.name && *t == target && *r == read)
            {
                cycles.push(cycle);
            }
        }
    }
    cycles.sort_by(|left, right| {
        (&left.0.name, &left.1.1, &left.2.1).cmp(&(&right.0.name, &right.1.1, &right.2.1))
    });
    cycles
        .into_iter()
        .map(|(audit, target, read)| diagnostic(request, audit, target, read))
        .collect()
}

fn gate(audit: &AuditGate) -> Option<Gate<'_>> {
    let target = audit.target.as_ref()?;
    let reads: Vec<&ResourceKey> = extra_reads(audit, target);
    (!reads.is_empty()).then_some(Gate { target, reads })
}

fn extra_reads<'a>(audit: &'a AuditGate, target: &ResourceKey) -> Vec<&'a ResourceKey> {
    audit
        .scope_deps
        .iter()
        .filter(|read| *read != target && READABLE_TYPES.contains(&read.0.as_str()))
        .collect()
}

/// `_gate_edges`: a source target gates the models it triggers, sorted by name.
fn edges_of(
    gate: &Gate<'_>,
    triggers: &HashMap<ResourceKey, HashSet<ResourceKey>>,
) -> Vec<GateEdge> {
    let gated: Vec<ResourceKey> = if gate.target.0 == SOURCE_TYPE {
        let mut keys: Vec<ResourceKey> = triggers
            .get(gate.target)
            .map(|keys| keys.iter().cloned().collect())
            .unwrap_or_default();
        keys.sort_by(|left, right| left.1.cmp(&right.1));
        keys
    } else {
        vec![gate.target.clone()]
    };
    let mut edges: Vec<GateEdge> = Vec::new();
    for read in &gate.reads {
        for key in &gated {
            edges.push(GateEdge {
                gated: key.clone(),
                read: (*read).clone(),
            });
        }
    }
    edges
}

fn diagnostic(
    request: &ReferenceRequest,
    audit: &AuditGate,
    target: &ResourceKey,
    read: &ResourceKey,
) -> ReferenceDiagnostic {
    let path: Option<String> = request
        .audits
        .iter()
        .rev()
        .find(|other| other.name == audit.name)
        .map(|other| other.path.clone());
    ReferenceDiagnostic {
        code: AUDIT_GATE_CODE,
        message: format!(
            "Audit '{}' on {} reads {}, which depends on '{}'; an attached audit gates its \
             target, so it cannot wait for a resource built from that target",
            audit.name,
            described(target),
            described(read),
            target.1
        ),
        help: format!(
            "write a singular audit under audits/singular/ that references both '{}' and '{}'; \
             it runs once both are built",
            target.1, read.1
        ),
        path,
        owner: None,
        line: None,
        resource: Some(target.clone()),
    }
}

fn described(key: &ResourceKey) -> String {
    let label: &str = match key.0.as_str() {
        UDF_TYPE => "function",
        TABLE_FUNCTION_TYPE => "table function",
        MODEL_TYPE | SOURCE_TYPE | SEED_TYPE => key.0.as_str(),
        other => other,
    };
    format!("{label} '{}'", key.1)
}
