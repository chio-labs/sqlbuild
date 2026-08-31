use crate::models::Fault;
use crate::rules::models::ProjectEvaluationRequest;

pub(crate) fn evaluate_project(
    request: ProjectEvaluationRequest<'_>,
) -> Result<Vec<Fault>, String> {
    let mut faults = crate::rules::_helpers::domain_layout::evaluate_project(&request);
    faults.extend(crate::rules::_helpers::sql_test_policy::evaluate_project(
        request,
    )?);
    Ok(faults)
}
