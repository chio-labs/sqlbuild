//! Every facade entry of `sqlbuild._native_host`.

use crate::entries::models::{HostEdge, HostEntry, HostKind};

/// Every facade entry, in `FacadeHost` order.
pub(crate) const ENTRIES: &[HostEntry] = &[
    HostEntry {
        name: "package_file",
        kind: HostKind::Value,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "dispatch_with_compute_logs",
        kind: HostKind::Function,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "provider_settings_inputs",
        kind: HostKind::Function,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "startup_inputs",
        kind: HostKind::Function,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "CompileReuseRequest",
        kind: HostKind::Class,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "AuditEvaluationMode",
        kind: HostKind::Class,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "AuditOutcome",
        kind: HostKind::Class,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "AuditSeverity",
        kind: HostKind::Class,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "ThresholdOperator",
        kind: HostKind::Class,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "AttachedAuditTargetKind",
        kind: HostKind::Class,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "FunctionLanguage",
        kind: HostKind::Class,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "SqlTestMode",
        kind: HostKind::Class,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "CursorAlgebraError",
        kind: HostKind::Exception,
        edge: HostEdge::Facade,
    },
    HostEntry {
        name: "SharedInputError",
        kind: HostKind::Exception,
        edge: HostEdge::Facade,
    },
];
