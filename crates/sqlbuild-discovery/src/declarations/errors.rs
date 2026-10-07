//! Why a declaration scan stopped: an authored layout failure or a whole-stage deferral.

use crate::models::{DiscoveryFailure, StageDeferral};

pub(crate) enum ScanError {
    Failure(DiscoveryFailure),
    Deferral(StageDeferral),
}

impl From<StageDeferral> for ScanError {
    fn from(deferral: StageDeferral) -> Self {
        Self::Deferral(deferral)
    }
}
