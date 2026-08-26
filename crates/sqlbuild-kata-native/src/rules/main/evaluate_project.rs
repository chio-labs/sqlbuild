use crate::models::Fault;
use crate::rules::models::ProjectEvaluationRequest;

pub(crate) fn evaluate_project(
    request: ProjectEvaluationRequest<'_>,
) -> Result<Vec<Fault>, String> {
    crate::rules::_helpers::sql_test_policy::evaluate_project(request)
}
