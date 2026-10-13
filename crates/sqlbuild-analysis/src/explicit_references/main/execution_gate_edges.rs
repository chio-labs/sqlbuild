//! The ordering edges attached audits and model hooks add to execution.

use crate::explicit_references::_helpers::audit_gates::gate_edges;
use crate::explicit_references::_helpers::hook_reads::hook_edges;
use crate::explicit_references::models::{ExecutionGateEdges, ExecutionGateRequest};

/// Python's `attached_audit_gate_edges` and `hook_read_edges`, in its order.
#[must_use]
pub fn execution_gate_edges(request: &ExecutionGateRequest) -> ExecutionGateEdges {
    ExecutionGateEdges {
        audit_gates: gate_edges(&request.resources, &request.audits),
        hook_reads: hook_edges(&request.models, &request.hooks),
    }
}
