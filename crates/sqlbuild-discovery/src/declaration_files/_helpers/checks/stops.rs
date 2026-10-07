//! Why native parsing of one declaration file stopped.

use crate::models::DiscoveryFailure;

/// The first failure Python raises for the file, or a file only the Python parser reproduces.
#[derive(Clone, Debug, PartialEq)]
pub(crate) enum ParseStop {
    Failed(DiscoveryFailure),
    Deferred,
}

impl From<DiscoveryFailure> for ParseStop {
    fn from(failure: DiscoveryFailure) -> Self {
        Self::Failed(failure)
    }
}
