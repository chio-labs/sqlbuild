//! Writer configuration, delivery streams, priorities and the delivery summary.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use crate::records::models::{DeliveryCounts, InvocationContext, RowEnvelope};
use crate::writer::_helpers::delivery::Shared;

/// The datasets whose delivery is accounted separately.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum DeliveryStream {
    Invocation,
    Output,
    Events,
    Diagnostics,
    Artifacts,
}

impl DeliveryStream {
    pub const ALL: [Self; 5] = [
        Self::Invocation,
        Self::Output,
        Self::Events,
        Self::Diagnostics,
        Self::Artifacts,
    ];

    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Invocation => "invocation",
            Self::Output => "output",
            Self::Events => "events",
            Self::Diagnostics => "diagnostics",
            Self::Artifacts => "artifacts",
        }
    }

    #[must_use]
    pub fn index(self) -> usize {
        match self {
            Self::Invocation => 0,
            Self::Output => 1,
            Self::Events => 2,
            Self::Diagnostics => 3,
            Self::Artifacts => 4,
        }
    }
}

/// Queue priority, lowest first; a full queue displaces the oldest record of the lowest priority below the arriving one.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Priority {
    DebugDiagnostic = 0,
    Artifact = 1,
    Output = 2,
    Diagnostic = 3,
    Lifecycle = 4,
    Terminal = 5,
    FailedTerminal = 6,
    Context = 7,
}

impl Priority {
    pub const COUNT: usize = 8;
}

/// What one writer session needs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SessionConfig {
    pub store_path: PathBuf,
    pub envelope: RowEnvelope,
    pub context: InvocationContext,
    pub retention_days: u32,
    pub shutdown_timeout: Duration,
    pub diagnostics_min_severity: String,
    /// Bytes of each output stream recorded, the first and last half; `None` records everything.
    pub max_output_bytes: Option<u64>,
    pub heartbeat_interval: Duration,
    pub setup_budget: Duration,
    /// Whether this session runs retention maintenance after delivery.
    pub maintenance: bool,
    pub maintenance_owner: String,
}

/// How table setup went.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SetupOutcome {
    Ready,
    /// The store cannot be created or written for lack of permission.
    PermissionDenied {
        reason: String,
    },
    Failed {
        reason: String,
    },
}

/// The delivery accounting of a closed session.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DeliverySummary {
    pub streams: Vec<(DeliveryStream, DeliveryCounts)>,
    pub flush_complete: bool,
    pub degraded_reason: Option<String>,
}

impl DeliverySummary {
    /// Every stream's counts added together.
    #[must_use]
    pub fn total(&self) -> DeliveryCounts {
        self.streams
            .iter()
            .fold(DeliveryCounts::default(), |mut total, (_, counts)| {
                total.accepted += counts.accepted;
                total.delivered += counts.delivered;
                total.filtered += counts.filtered;
                total.dropped += counts.dropped;
                total.failed += counts.failed;
                total.conflicts += counts.conflicts;
                total
            })
    }
}

/// A running Recall session. Producers only touch the queue; the delivery thread writes.
#[derive(Debug)]
pub struct RecallSession {
    pub(crate) shared: Arc<Shared>,
    pub(crate) shutdown_timeout: Duration,
    pub(crate) min_severity: usize,
}
