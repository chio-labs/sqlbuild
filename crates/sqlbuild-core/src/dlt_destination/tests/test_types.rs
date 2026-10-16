use crate::dlt_destination::models::DltDestinationPlan;

pub(super) struct DestinationPlanTestCase {
    pub(super) description: &'static str,
    pub(super) adapter: &'static str,
    pub(super) strings: &'static [(&'static str, &'static str)],
    pub(super) port: Option<&'static str>,
    pub(super) destination_keys: &'static [&'static str],
    pub(super) dataset_name: Option<&'static str>,
    pub(super) expected_plan: Result<DltDestinationPlan, &'static str>,
}
