//! `effective_concurrency`: the worker limit of one command and the layer it came from.

use crate::effective::models::{ConcurrencyLayers, ConcurrencySource, EffectiveConcurrency};

/// `--concurrency`, else the target's `concurrency`, else the local-then-project setting.
#[must_use]
pub fn effective_concurrency(layers: &ConcurrencyLayers<'_>) -> EffectiveConcurrency {
    if let Some(limit) = layers.requested {
        return EffectiveConcurrency {
            limit,
            source: ConcurrencySource::CommandLine,
        };
    }
    if let Some((target, limit)) = layers.target {
        return EffectiveConcurrency {
            limit,
            source: ConcurrencySource::Target(target.to_owned()),
        };
    }
    EffectiveConcurrency {
        limit: layers.settings,
        source: if layers.local_override {
            ConcurrencySource::LocalSettings
        } else {
            ConcurrencySource::ProjectSettings
        },
    }
}
