use crate::dbt_plan::models::DbtPlanArgvs;

pub(super) fn texts(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// The primary, SQLBuild and supplemental command lines in order.
pub(super) fn flattened(argvs: DbtPlanArgvs) -> Vec<Vec<String>> {
    let mut all: Vec<Vec<String>> = vec![argvs.dbt_command_argv];
    all.extend(argvs.sqlbuild_command_argvs);
    all.extend(argvs.supplemental_dbt_command_argvs);
    all
}
