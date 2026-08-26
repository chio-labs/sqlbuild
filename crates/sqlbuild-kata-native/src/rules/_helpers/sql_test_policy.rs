use crate::models::{
    DeclarationKind, Fault, ResourceKind, RuleMetadata, ScopeResource, SqlScenarioFact,
    SqlTestFact, SqlTestMode,
};
use crate::rules::models::ProjectEvaluationRequest;
use std::path::Path;

const UNIT_ROOT: &str = "tests/unit";
const SCENARIO_ROOT: &str = "tests/scenarios";

pub(crate) fn evaluate_project(
    evaluation: ProjectEvaluationRequest<'_>,
) -> Result<Vec<Fault>, String> {
    let mut faults: Vec<Fault> = Vec::new();
    let mut tests: Vec<&SqlTestFact> = evaluation.request.sql_tests.iter().collect();
    tests.sort_by(|left, right| {
        (&left.source_path, left.block_index).cmp(&(&right.source_path, right.block_index))
    });
    let mut scenarios: Vec<&SqlScenarioFact> = evaluation.request.sql_scenarios.iter().collect();
    scenarios.sort_by(|left, right| left.source_path.cmp(&right.source_path));

    if let Some(rule) = evaluation.selected.get("SQBKT001") {
        faults.extend(canonical_roots(rule, &tests, &scenarios));
    }
    if let Some(rule) = evaluation.selected.get("SQBKT002") {
        faults.extend(filenames(rule, &tests, &scenarios));
    }
    if let Some(rule) = evaluation.selected.get("SQBKT003") {
        faults.extend(mirroring(rule, &evaluation, &tests));
    }
    if let Some(rule) = evaluation.selected.get("SQBKT004") {
        faults.extend(structured_names(rule, &evaluation, &tests));
    }
    if let Some(rule) = evaluation.selected.get("SQBKT101") {
        faults.extend(scenario_descriptions(rule, &scenarios));
    }
    Ok(faults)
}

fn canonical_roots(
    rule: &RuleMetadata,
    tests: &[&SqlTestFact],
    scenarios: &[&SqlScenarioFact],
) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for test in tests {
        if test.ownership_root != UNIT_ROOT || !is_beneath(&test.source_path, UNIT_ROOT) {
            faults.push(path_fault(
                rule,
                &test.source_path,
                format!(
                    "unit test block {} is outside the canonical {UNIT_ROOT}/ root",
                    test.block_index
                ),
                format!("Move this unit test beneath {UNIT_ROOT}/."),
            ));
        }
    }
    for scenario in scenarios {
        if scenario.ownership_root != SCENARIO_ROOT
            || !is_beneath(&scenario.source_path, SCENARIO_ROOT)
        {
            faults.push(path_fault(
                rule,
                &scenario.source_path,
                format!("scenario is outside the canonical {SCENARIO_ROOT}/ root"),
                format!("Move this scenario beneath {SCENARIO_ROOT}/."),
            ));
        }
    }
    faults
}

fn filenames(
    rule: &RuleMetadata,
    tests: &[&SqlTestFact],
    scenarios: &[&SqlScenarioFact],
) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for test in tests {
        let stem = file_stem(&test.source_path);
        let valid = stem.strip_prefix("test_").is_some_and(valid_unit_filename);
        let behavior_matches = test.explicit_name.as_deref().is_none_or(|name| {
            filename_behavior(stem)
                .zip(structured_name(name).map(|(_, behavior)| behavior))
                .is_none_or(|(slug, behavior)| behavior_slug_matches(slug, behavior))
        });
        if !valid || !behavior_matches {
            faults.push(path_fault(
                rule,
                &test.source_path,
                format!(
                    "unit test block {} filename does not follow test_<subject>__<behavior>.sql",
                    test.block_index
                ),
                test.explicit_name
                    .as_deref()
                    .and_then(structured_name)
                    .map_or_else(
                        || "Rename this file to test_<subject>__<behavior>.sql.".to_owned(),
                        |(subject, behavior)| {
                            format!(
                                "Rename this file to test_{}__{}.sql.",
                                slug(subject),
                                slug(behavior)
                            )
                        },
                    ),
            ));
        }
    }
    for scenario in scenarios {
        if !valid_filename_parts(file_stem(&scenario.source_path)) {
            faults.push(path_fault(
                rule,
                &scenario.source_path,
                "scenario filename does not follow <subject>__<behavior>.sql".into(),
                "Rename this file to <business subject>__<behavior>.sql.".into(),
            ));
        }
    }
    faults
}

fn mirroring(
    rule: &RuleMetadata,
    evaluation: &ProjectEvaluationRequest<'_>,
    tests: &[&SqlTestFact],
) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for test in tests {
        let Some(expected_parent) = expected_parent(evaluation, test) else {
            continue;
        };
        let actual_parent = Path::new(&test.source_path)
            .parent()
            .map(|path| path.to_string_lossy().replace('\\', "/"))
            .unwrap_or_default();
        if actual_parent != expected_parent {
            faults.push(path_fault(
                rule,
                &test.source_path,
                format!(
                    "unit test block {} resolves to resources mirrored by {expected_parent}/",
                    test.block_index
                ),
                format!("Move this test file beneath {expected_parent}/."),
            ));
        }
    }
    faults
}

fn structured_names(
    rule: &RuleMetadata,
    evaluation: &ProjectEvaluationRequest<'_>,
    tests: &[&SqlTestFact],
) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for test in tests {
        let Some(name) = test.explicit_name.as_deref() else {
            faults.push(name_fault(
                rule,
                test,
                "the TEST block has no explicit name",
                None,
            ));
            continue;
        };
        let Some((subject, behavior)) = structured_name(name) else {
            faults.push(name_fault(
                rule,
                test,
                "the TEST name must contain a nonempty subject and behavior separated by ':'",
                None,
            ));
            continue;
        };
        if generic(subject) || generic(behavior) {
            faults.push(name_fault(
                rule,
                test,
                "the TEST name uses a generic subject or behavior",
                None,
            ));
            continue;
        }
        let allowed = allowed_subjects(evaluation, test);
        if !allowed.is_empty() && !subject_matches(subject, &allowed) {
            faults.push(name_fault(
                rule,
                test,
                &format!(
                    "the TEST subject '{}' does not identify its resolved target; expected {}",
                    subject,
                    allowed.join(" or ")
                ),
                allowed.first().map(String::as_str),
            ));
        }
    }
    faults
}

fn scenario_descriptions(rule: &RuleMetadata, scenarios: &[&SqlScenarioFact]) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for scenario in scenarios {
        let description = scenario.description.as_deref().unwrap_or("").trim();
        let behavior = file_stem(&scenario.source_path)
            .split_once("__")
            .map(|(_, value)| value)
            .unwrap_or("");
        if description.is_empty() || generic(description) || generic(behavior) {
            faults.push(path_fault(
                rule,
                &scenario.source_path,
                "scenario description or filename uses a generic case label".into(),
                "Write a concrete business description and a <subject>__<behavior>.sql filename."
                    .into(),
            ));
        }
    }
    faults
}

fn expected_parent(
    evaluation: &ProjectEvaluationRequest<'_>,
    test: &SqlTestFact,
) -> Option<String> {
    match test.mode {
        SqlTestMode::Model => {
            let mut directories: Vec<Vec<String>> = Vec::new();
            for name in &test.target_model_names {
                let resource = scope_resource(evaluation, ResourceKind::Model, name)?;
                directories.push(relative_parent(resource)?);
            }
            if directories.is_empty() {
                return None;
            }
            let common = common_components(&directories);
            Some(if common.is_empty() {
                format!(
                    "{UNIT_ROOT}/{}",
                    evaluation.request.config.sql_tests.pipeline_directory
                )
            } else {
                format!("{UNIT_ROOT}/{}", common.join("/"))
            })
        }
        SqlTestMode::Macro => direct_expected_parent(&macro_parent_components(evaluation, test)?),
        SqlTestMode::Udf | SqlTestMode::TableFn => {
            direct_expected_parent(&function_parent_components(evaluation, test)?)
        }
    }
}

fn macro_parent_components(
    evaluation: &ProjectEvaluationRequest<'_>,
    test: &SqlTestFact,
) -> Option<Vec<Vec<String>>> {
    let mut parents: Vec<Vec<String>> = Vec::new();
    for resource in &test.tested_resources {
        let declaration = evaluation
            .request
            .scope_index
            .declarations
            .iter()
            .find(|item| {
                matches!(item.kind, DeclarationKind::Macro) && item.name == resource.name
            })?;
        parents.push(direct_parent_components(
            &declaration.path,
            &declaration.ownership_root,
        )?);
    }
    Some(parents)
}

fn function_parent_components(
    evaluation: &ProjectEvaluationRequest<'_>,
    test: &SqlTestFact,
) -> Option<Vec<Vec<String>>> {
    let mut parents: Vec<Vec<String>> = Vec::new();
    for resource in &test.tested_resources {
        let fact = scope_resource(evaluation, ResourceKind::Function, &resource.name)?;
        parents.push(direct_parent_components(&fact.path, &fact.ownership_root)?);
    }
    Some(parents)
}

fn direct_parent_components(path: &str, root: &str) -> Option<Vec<String>> {
    let path: Vec<&str> = path.split('/').collect();
    let root: Vec<&str> = root.split('/').collect();
    if path.len() <= root.len() || path.get(..root.len()) != Some(root.as_slice()) {
        return None;
    }
    Some(
        path[..path.len() - 1]
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
    )
}

fn direct_expected_parent(parents: &[Vec<String>]) -> Option<String> {
    let common = common_components(parents);
    (!common.is_empty()).then(|| format!("{UNIT_ROOT}/{}", common.join("/")))
}

fn allowed_subjects(evaluation: &ProjectEvaluationRequest<'_>, test: &SqlTestFact) -> Vec<String> {
    if !matches!(test.mode, SqlTestMode::Model) {
        return test
            .tested_resources
            .iter()
            .map(|resource| resource.name.clone())
            .collect();
    }
    if test.target_model_names.len() == 1 {
        return test.target_model_names.clone();
    }
    if test.target_model_names.len() > 1 {
        let mut directories: Vec<Vec<String>> = Vec::new();
        for name in &test.target_model_names {
            let Some(resource) = scope_resource(evaluation, ResourceKind::Model, name) else {
                return Vec::new();
            };
            let Some(parent) = relative_parent(resource) else {
                return Vec::new();
            };
            directories.push(parent);
        }
        let common = common_components(&directories);
        return common
            .last()
            .map_or_else(|| vec!["pipeline".into()], |domain| vec![domain.clone()]);
    }
    Vec::new()
}

fn scope_resource<'a>(
    evaluation: &'a ProjectEvaluationRequest<'_>,
    kind: ResourceKind,
    name: &str,
) -> Option<&'a ScopeResource> {
    evaluation
        .request
        .scope_index
        .resources
        .iter()
        .find(|item| same_resource_kind(&item.kind, &kind) && item.name == name)
}

fn same_resource_kind(left: &ResourceKind, right: &ResourceKind) -> bool {
    matches!(
        (left, right),
        (ResourceKind::Model, ResourceKind::Model)
            | (ResourceKind::Function, ResourceKind::Function)
    )
}

fn relative_parent(resource: &ScopeResource) -> Option<Vec<String>> {
    let path: Vec<&str> = resource.path.split('/').collect();
    let root: Vec<&str> = resource.ownership_root.split('/').collect();
    if path.len() <= root.len() || path.get(..root.len()) != Some(root.as_slice()) {
        return None;
    }
    Some(
        path[root.len()..path.len() - 1]
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
    )
}

fn common_components(values: &[Vec<String>]) -> Vec<String> {
    let Some(first) = values.first() else {
        return Vec::new();
    };
    let mut common: Vec<String> = Vec::new();
    for (index, value) in first.iter().enumerate() {
        let mut shared = true;
        for candidate in values {
            if candidate.get(index) != Some(value) {
                shared = false;
                break;
            }
        }
        if !shared {
            break;
        }
        common.push(value.clone());
    }
    common
}

fn name_fault(
    rule: &RuleMetadata,
    test: &SqlTestFact,
    detail: &str,
    proposed_subject: Option<&str>,
) -> Fault {
    path_fault(
        rule,
        &test.source_path,
        format!("unit test block {} {detail}", test.block_index),
        format!(
            "Add name \"{}: <expected behavior>\" to this TEST header.",
            proposed_subject.unwrap_or("<resolved subject>")
        ),
    )
}

fn path_fault(rule: &RuleMetadata, path: &str, message: String, remediation: String) -> Fault {
    Fault {
        code: rule.code.clone(),
        path: path.to_owned(),
        line: 1,
        column: 1,
        message,
        remediation,
    }
}

fn is_beneath(path: &str, root: &str) -> bool {
    path.strip_prefix(root)
        .is_some_and(|suffix| suffix.starts_with('/'))
}

fn file_stem(path: &str) -> &str {
    let filename = path.rsplit('/').next().unwrap_or(path);
    filename.strip_suffix(".sql").unwrap_or(filename)
}

fn valid_filename_parts(value: &str) -> bool {
    let Some((subject, behavior)) = value.split_once("__") else {
        return false;
    };
    !subject.is_empty()
        && !behavior.is_empty()
        && slug(subject) == subject
        && slug(behavior) == behavior
}

fn valid_unit_filename(value: &str) -> bool {
    if value.contains("__") {
        return valid_filename_parts(value);
    }
    !value.is_empty() && slug(value) == value
}

fn filename_behavior(stem: &str) -> Option<&str> {
    stem.split_once("__").map(|(_, behavior)| behavior)
}

fn structured_name(name: &str) -> Option<(&str, &str)> {
    let (subject, behavior) = name.split_once(':')?;
    let subject = subject.trim();
    let behavior = behavior.trim();
    (!subject.is_empty() && !behavior.is_empty()).then_some((subject, behavior))
}

fn behavior_slug_matches(filename: &str, behavior: &str) -> bool {
    let behavior = slug(behavior);
    behavior == filename || behavior.starts_with(&format!("{filename}_"))
}

fn subject_matches(subject: &str, allowed: &[String]) -> bool {
    let normalized = slug(subject);
    for value in allowed {
        let candidate = slug(value);
        if normalized == candidate {
            return true;
        }
        if candidate == crate::constants::PIPELINE_SUBJECT
            && normalized
                .split('_')
                .any(|component| component == crate::constants::PIPELINE_SUBJECT)
        {
            return true;
        }
    }
    false
}

fn generic(value: &str) -> bool {
    let normalized = slug(value);
    matches!(
        normalized.as_str(),
        crate::constants::GENERIC_TEST_NAME
            | crate::constants::GENERIC_WORKS_NAME
            | crate::constants::GENERIC_BASIC_NAME
            | crate::constants::GENERIC_SCENARIO_NAME
            | crate::constants::GENERIC_CASE_NAME
    ) || normalized
        .strip_prefix("case_")
        .is_some_and(|suffix| suffix.chars().all(|character| character.is_ascii_digit()))
}

fn slug(value: &str) -> String {
    let mut output = String::new();
    let mut separator = false;
    for character in value.chars().flat_map(char::to_lowercase) {
        if character.is_alphanumeric() {
            if separator && !output.is_empty() {
                output.push('_');
            }
            output.push(character);
            separator = false;
        } else {
            separator = true;
        }
    }
    output
}
