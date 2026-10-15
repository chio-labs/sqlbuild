use crate::custom_host_pool::models::HostSlice;
use crate::custom_host_pool::types::{HostInvocation, HostPlan};

pub(super) struct HostCapacityTestCase {
    pub(super) description: &'static str,
    pub(super) proc_cgroup: &'static [u8],
    pub(super) files: &'static [(&'static str, &'static [u8])],
    pub(super) expected_cores: usize,
}

pub(super) struct HostPlanTestCase {
    pub(super) description: &'static str,
    pub(super) plan: HostPlan,
    pub(super) invocations: Vec<HostInvocation>,
    pub(super) hosts: usize,
    pub(super) expected_plans: Vec<HostPlan>,
}

pub(super) struct HostCountTestCase {
    pub(super) description: &'static str,
    pub(super) invocations: usize,
    pub(super) cores: usize,
    pub(super) min_invocations_per_host: usize,
    pub(super) expected_hosts: usize,
}

pub(super) struct DecodeTestCase {
    pub(super) description: &'static str,
    pub(super) response: serde_json::Value,
    pub(super) expected_slice: Result<HostSlice, String>,
}

pub(super) struct MergeTestCase {
    pub(super) description: &'static str,
    pub(super) slices: Vec<HostSlice>,
    pub(super) order: Vec<HostInvocation>,
    pub(super) expected_order: Vec<HostInvocation>,
    pub(super) expected_untracked: Vec<String>,
    pub(super) expected_observed: Vec<(Vec<String>, Option<String>)>,
}
