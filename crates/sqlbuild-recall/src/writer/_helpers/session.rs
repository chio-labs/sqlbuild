//! The session handle: producers queue records; `close` flushes within the shutdown budget.

use std::time::{Duration, Instant, SystemTime};

use crate::records::constants::{
    ARTIFACT_DIGEST_PREFIX, EXECUTED_SQL_ROLE, SEVERITY_ORDER, SQL_ARTIFACT_KIND, SQL_MEDIA_TYPE,
};
use crate::records::errors::RecordError;
use crate::records::main::artifact_rows::artifact_rows;
use crate::records::main::diagnostic_input_from_json::diagnostic_input_from_json;
use crate::records::main::diagnostic_row::diagnostic_row;
use crate::records::main::event_row::event_row;
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::sha256_hex::sha256_hex;
use crate::records::models::{ArtifactInput, OutputStream, RecallValue};
use crate::store::constants::MAINTENANCE_BUDGET_MS;
use crate::writer::_helpers::delivery::locked;
use crate::writer::models::{
    DeliveryStream, DeliverySummary, Priority, RecallSession, SetupOutcome,
};

pub(crate) fn severity_rank(severity: &str) -> usize {
    SEVERITY_ORDER
        .iter()
        .position(|candidate| *candidate == severity)
        .unwrap_or(0)
}

fn event_priority(severity: &str) -> Priority {
    match severity {
        "error" => Priority::FailedTerminal,
        "info" => Priority::Terminal,
        _ => Priority::Lifecycle,
    }
}

impl RecallSession {
    /// Wait up to `budget` for table setup; `None` while it is still running.
    pub fn wait_for_setup(&self, budget: Duration) -> Option<SetupOutcome> {
        let deadline = Instant::now() + budget;
        let mut setup = self
            .shared
            .setup
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        while setup.is_none() {
            let now = Instant::now();
            if now >= deadline {
                return None;
            }
            setup = self
                .shared
                .setup_done
                .wait_timeout(setup, deadline - now)
                .unwrap_or_else(std::sync::PoisonError::into_inner)
                .0;
        }
        setup.clone()
    }

    /// The invocation this session records.
    #[must_use]
    pub fn invocation_id(&self) -> String {
        locked(&self.shared.state).envelope.invocation_id.clone()
    }

    /// Accept bytes a process stream accepted.
    pub fn append_output(&self, stream: OutputStream, data: &[u8]) {
        let mut state = locked(&self.shared.state);
        state.append_output(stream, data, SystemTime::now());
        self.shared.wake.notify_one();
    }

    /// Queue one lifecycle event from its canonical JSON.
    pub fn publish_event(&self, event_json: &str) -> Result<(), RecordError> {
        let mut state = locked(&self.shared.state);
        let row = event_row(&state.envelope, event_json)?;
        let priority = match row.value("severity") {
            Some(RecallValue::Text(severity)) => event_priority(severity),
            _ => Priority::Lifecycle,
        };
        state.push(vec![row], DeliveryStream::Events, priority);
        self.shared.wake.notify_one();
        Ok(())
    }

    /// Queue one diagnostic from its canonical JSON, when at or above the minimum severity.
    pub fn publish_diagnostic(&self, diagnostic_json: &str) -> Result<(), RecordError> {
        let mut state = locked(&self.shared.state);
        let sequence = state.diagnostic_sequence;
        let diagnostic = diagnostic_input_from_json(diagnostic_json, sequence)?;
        let rank = severity_rank(&diagnostic.severity);
        if rank < self.min_severity {
            return Ok(());
        }
        state.diagnostic_sequence += 1;
        let priority = if rank >= severity_rank("warning") {
            Priority::Diagnostic
        } else {
            Priority::DebugDiagnostic
        };
        let row = diagnostic_row(&state.envelope, &diagnostic);
        state.push(vec![row], DeliveryStream::Diagnostics, priority);
        self.shared.wake.notify_one();
        Ok(())
    }

    /// Queue the SQL a statement executed, once per digest per invocation.
    pub fn publish_sql(&self, sql: &str, statement_id: Option<&str>, resource_id: Option<&str>) {
        let digest = format!("{ARTIFACT_DIGEST_PREFIX}{}", sha256_hex(sql.as_bytes()));
        let mut state = locked(&self.shared.state);
        if !state.artifacts_seen.insert(digest.clone()) {
            return;
        }
        let artifact = ArtifactInput {
            ref_id: statement_id.map_or_else(|| digest.clone(), str::to_owned),
            digest,
            kind: SQL_ARTIFACT_KIND.to_owned(),
            media_type: SQL_MEDIA_TYPE.to_owned(),
            content: sql.as_bytes().to_vec(),
            seen_at: format_timestamp(SystemTime::now()),
            role: EXECUTED_SQL_ROLE.to_owned(),
            statement_id: statement_id.map(str::to_owned),
            resource_id: resource_id.map(str::to_owned),
        };
        let rows = artifact_rows(&state.envelope, &artifact).to_vec();
        state.push(rows, DeliveryStream::Artifacts, Priority::Artifact);
        self.shared.wake.notify_one();
    }

    /// Count records a replacement sink filtered out of `stream`.
    pub fn record_filtered(&self, stream: DeliveryStream, count: u64) {
        let mut state = locked(&self.shared.state);
        let counts = state.counts_mut(stream);
        counts.accepted += count;
        counts.filtered += count;
    }

    /// Count records a replacement sink failed on in `stream`.
    pub fn record_failed(&self, stream: DeliveryStream, count: u64) {
        let mut state = locked(&self.shared.state);
        let counts = state.counts_mut(stream);
        counts.accepted += count;
        counts.failed += count;
    }

    /// The accounting so far.
    #[must_use]
    pub fn summary(&self) -> DeliverySummary {
        let state = locked(&self.shared.state);
        DeliverySummary {
            streams: DeliveryStream::ALL
                .iter()
                .map(|stream| (*stream, state.counts[stream.index()]))
                .collect(),
            flush_complete: state.finished && state.queued() == 0 && state.degraded.is_none(),
            degraded_reason: state.degraded.clone(),
        }
    }

    /// Flush within the shutdown budget, write the delivery rows and return the accounting. Records still queued at the deadline are counted as dropped.
    pub fn close(&self) -> DeliverySummary {
        let deadline = Instant::now() + self.shutdown_timeout;
        let wait_until = deadline + Duration::from_millis(MAINTENANCE_BUDGET_MS + 500);
        {
            let mut state = locked(&self.shared.state);
            if !state.closing {
                state.closing = true;
                state.deadline = Some(deadline);
                state.flush_output();
            }
            self.shared.wake.notify_all();
            while !state.finished {
                let now = Instant::now();
                if now >= wait_until {
                    state.rejecting = true;
                    state.drop_all();
                    state.degraded.get_or_insert_with(|| {
                        "Recall delivery did not finish within the shutdown timeout".to_owned()
                    });
                    break;
                }
                state = self
                    .shared
                    .wake
                    .wait_timeout(state, wait_until - now)
                    .unwrap_or_else(std::sync::PoisonError::into_inner)
                    .0;
            }
        }
        self.summary()
    }
}
