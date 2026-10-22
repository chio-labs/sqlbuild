//! The store interfaces the delivery thread writes through.

use std::time::{Duration, Instant};

use crate::records::models::{RecallRow, RowEnvelope};
use crate::store::errors::StoreError;
use crate::store::models::{InsertOutcome, MaintenanceRequest};

/// An open store the delivery thread alone writes to.
pub trait RecallStore: Send {
    /// Write `rows` idempotently by key: an equal duplicate is a no-op; a key already stored with different content keeps the stored row and is reported. Waits end by `give_up`.
    fn insert(&self, rows: &[RecallRow], give_up: Instant) -> Result<InsertOutcome, StoreError>;

    /// Retention work after delivery, within `request.budget`; best effort.
    fn maintain(&self, _request: &MaintenanceRequest) {}

    /// Notices for the user gathered since the last call, such as a retention conflict.
    fn take_notices(&mut self) -> Vec<String> {
        Vec::new()
    }

    /// Release the connection; called once when delivery ends.
    fn close(&mut self) {}
}

/// Opens a store hosted outside this crate, such as ClickHouse through its adapter, on the delivery thread.
pub trait RecallStoreOpener: Send + Sync + std::fmt::Debug {
    /// Connect and create or upgrade the tables, giving up on waits by `give_up`. A `Busy` error is retried until then.
    fn open(
        &self,
        envelope: &RowEnvelope,
        give_up: Instant,
    ) -> Result<Box<dyn RecallStore>, StoreError>;

    /// What opening did that the user should know although nothing is wrong, such as a database it created, gathered since the last call. Kept across failed and retried opens, so each is reported exactly once.
    fn take_information(&self) -> Vec<String> {
        Vec::new()
    }

    /// Most rows one insert batch takes.
    fn batch_rows(&self) -> usize;

    /// Longest wait for a batch to fill once its first record is queued.
    fn batch_window(&self) -> Duration;
}
