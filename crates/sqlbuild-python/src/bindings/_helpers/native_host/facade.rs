//! Public facade entry points: the CLI entry point, compile reuse and the package itself.

use crate::bindings::_helpers::native_host::models::{HostEdge, HostEntry, HostId, HostKind};

/// One facade entry of `sqlbuild._native_host`, indexing `ENTRIES`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum FacadeHost {
    PackageFile,
    DispatchWithComputeLogs,
    ProviderSettingsInputs,
    StartupInputs,
    CompileReuseRequest,
    AuditEvaluationMode,
    AuditOutcome,
    AuditSeverity,
    ThresholdOperator,
    AttachedAuditTargetKind,
    FunctionLanguage,
    SqlTestMode,
    CursorAlgebraError,
    SharedInputError,
}

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

impl FacadeHost {
    /// The entry's position in `HOST_ENTRIES`, usable in constant tables.
    pub(crate) const fn id(self) -> HostId {
        HostId {
            edge: HostEdge::Facade,
            index: self as usize,
        }
    }
}

impl From<FacadeHost> for HostId {
    fn from(entry: FacadeHost) -> Self {
        entry.id()
    }
}
