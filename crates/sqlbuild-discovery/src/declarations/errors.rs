//! Why a declaration scan stopped: an authored layout failure or a whole-stage failure.

use crate::models::{DiscoveryFailure, StageFailure};

pub(crate) enum ScanError {
    Failure(DiscoveryFailure),
    Stage(StageFailure),
}

impl From<StageFailure> for ScanError {
    fn from(failure: StageFailure) -> Self {
        Self::Stage(failure)
    }
}
