//! The host module and the one table of every entry native code may reach through it.

use crate::entries::_helpers::{adapter, executor, facade, third_party, user_code};
use crate::entries::models::HostEntry;

/// The only `sqlbuild` Python module native code imports by path.
pub const HOST_MODULE: &str = "sqlbuild._native_host";
/// The module a custom-rule host process runs with `python -m`, a user-code edge reached by path.
pub const CUSTOM_HOST_LAUNCH_MODULE: &str = "sqlbuild.rule_engine._helpers.host.custom_host_launch";
/// The host module function naming each entry's target module and attribute.
pub const HOST_TARGETS_FUNCTION: &str = "host_targets";
/// Every host entry, one group per edge in `HostEdge` order.
pub const HOST_ENTRIES: [&[HostEntry]; 5] = [
    adapter::ENTRIES,
    user_code::ENTRIES,
    executor::ENTRIES,
    third_party::ENTRIES,
    facade::ENTRIES,
];
