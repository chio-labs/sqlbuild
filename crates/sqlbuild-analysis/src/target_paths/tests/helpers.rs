use crate::target_paths::models::SqlTestPathFacts;

pub(super) fn facts(
    name: &str,
    case: Option<(&str, Option<i64>, &str)>,
    models: &[&str],
) -> SqlTestPathFacts {
    SqlTestPathFacts {
        name: name.to_owned(),
        source_path: case.map(|(source, _, _)| source.to_owned()),
        block_index: case.and_then(|(_, block, _)| block),
        case_name: case.map(|(_, _, case_name)| case_name.to_owned()),
        model_names: models.iter().map(|model| (*model).to_owned()).collect(),
    }
}
