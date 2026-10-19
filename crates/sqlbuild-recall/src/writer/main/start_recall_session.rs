//! `start_recall_session`: begin recording one invocation.

use std::sync::{Arc, Condvar, Mutex, OnceLock};

use crate::records::main::invocation_row::invocation_row;
use crate::writer::_helpers::delivery::{Shared, deliver, locked};
use crate::writer::_helpers::queue::WriterState;
use crate::writer::_helpers::session::severity_rank;
use crate::writer::models::{DeliveryStream, Priority, RecallSession, SessionConfig};

/// Start the delivery thread and queue the invocation's context row first, unless the config defers it.
#[must_use]
pub fn start_recall_session(config: SessionConfig) -> RecallSession {
    let mut state =
        WriterState::new(config.envelope.clone()).with_output_limit(config.max_output_bytes);
    if config.defer_context {
        state.held_context = Some(config.context.clone());
    } else {
        state.push(
            vec![invocation_row(&config.envelope, &config.context)],
            DeliveryStream::Invocation,
            Priority::Context,
        );
    }
    let shared = Arc::new(Shared {
        state: Mutex::new(state),
        wake: Condvar::new(),
        setup: Mutex::new(None),
        setup_done: Condvar::new(),
        output_replacement: OnceLock::new(),
    });
    let session = RecallSession {
        shared: Arc::clone(&shared),
        shutdown_timeout: config.shutdown_timeout,
        min_severity: severity_rank(&config.diagnostics_min_severity),
        delivery: Mutex::new(None),
    };
    let spawned = std::thread::Builder::new()
        .name("sqlbuild-recall".to_owned())
        .spawn(move || deliver(&shared, &config));
    match spawned {
        Ok(handle) => {
            *session
                .delivery
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(handle);
        }
        Err(error) => {
            let mut state = locked(&session.shared.state);
            state.degraded = Some(format!("cannot start the Recall delivery thread: {error}"));
            state.rejecting = true;
            state.drop_all();
            state.finished = true;
        }
    }
    session
}
