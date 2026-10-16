//! The host module and the one table of every entry native code may reach through it.

use crate::bindings::_helpers::native_host::models::HostEntry;
use crate::bindings::_helpers::native_host::{adapter, executor, facade, third_party, user_code};

/// The only `sqlbuild` Python module native code imports by path.
pub(crate) const HOST_MODULE: &str = "sqlbuild._native_host";
/// The module a custom-rule host process runs with `python -m`, a user-code edge reached by path.
pub(crate) const CUSTOM_HOST_LAUNCH_MODULE: &str =
    "sqlbuild.rule_engine._helpers.host.custom_host_launch";
/// The host module function naming each entry's target module and attribute.
pub(crate) const HOST_TARGETS_FUNCTION: &str = "host_targets";
/// Every host entry, one group per edge in `HostEdge` order.
pub(crate) const HOST_ENTRIES: [&[HostEntry]; 5] = [
    adapter::ENTRIES,
    user_code::ENTRIES,
    executor::ENTRIES,
    third_party::ENTRIES,
    facade::ENTRIES,
];
