//! Compile's explicit-reference checks over one compiled project, in Python's order.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::explicit_references::_helpers::audit_gates::{gate_diagnostics, gate_edges};
use crate::explicit_references::_helpers::hook_reads::{hook_diagnostics, unknown_read};
use crate::explicit_references::_helpers::python_sql::python_sql_report;
use crate::explicit_references::errors::ReferenceFailure;
use crate::explicit_references::models::{ReferenceReport, ReferenceRequest};

/// P005, P007 then P008 diagnostics and unmatched Python-SQL relations, or the error Python raises.
pub fn check_explicit_references(
    request: &ReferenceRequest,
) -> Result<ReferenceReport, ReferenceFailure> {
    catch_compiler_panic(|| Ok(checked(request)))
        .map_err(ReferenceFailure::Internal)
        .and_then(|outcome| outcome)
}

fn checked(request: &ReferenceRequest) -> Result<ReferenceReport, ReferenceFailure> {
    let python_sql: ReferenceReport = if request.enforce_explicit {
        python_sql_report(request)?
    } else {
        ReferenceReport::default()
    };
    let gates = gate_edges(request);
    let mut diagnostics = gate_diagnostics(request, &gates);
    if let Some(message) = unknown_read(request) {
        return Err(ReferenceFailure::CompileInput(message));
    }
    diagnostics.extend(hook_diagnostics(request, &gates));
    diagnostics.extend(python_sql.diagnostics);
    Ok(ReferenceReport {
        diagnostics,
        unmatched: python_sql.unmatched,
    })
}
