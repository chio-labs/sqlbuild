use crate::models::KataConfig;
use fensu_policy::policy::models::ProductRuleCodeGrammar;
use fensu_policy::policy::types::RuleCodeGrammar;
use std::path::Path;

pub(crate) fn load_config_json(project_dir: &Path) -> Result<String, String> {
    let config = load(project_dir)?;
    serde_json::to_string(&config).map_err(|error| error.to_string())
}

pub(crate) fn load(project_dir: &Path) -> Result<KataConfig, String> {
    let path = project_dir.join("sqlbuild_project.toml");
    let source = std::fs::read_to_string(&path).map_err(|error| {
        format!(
            "could not load kata config from {}: {error}",
            path.display()
        )
    })?;
    let root: toml::Table = toml::from_str(&source).map_err(|error| {
        format!(
            "could not load kata config from {}: {error}",
            path.display()
        )
    })?;
    let config = match root.get("kata") {
        None => KataConfig::default(),
        Some(value) => {
            validate_raw(value)?;
            value
                .clone()
                .try_into::<KataConfig>()
                .map_err(|error| format!("invalid kata config: {error}"))?
        }
    };
    validate(&config)?;
    Ok(config)
}

fn validate_raw(value: &toml::Value) -> Result<(), String> {
    let table = value
        .as_table()
        .ok_or_else(|| "kata must be a table".to_owned())?;
    let known = [
        "select",
        "ignore",
        "thresholds",
        "threshold_overrides",
        "rule_options",
        "rule_exceptions",
        "rule_ignores",
        "select_star_allow",
        "rule_paths",
        "rule_modules",
        "domains",
        "approved_source_tokens",
        "retired_source_tokens",
        "cte_name_whitelist",
        "cte_name_denylist",
        "sql_tests",
        "layout",
        "cache",
    ];
    let mut unknown: Vec<String> = table
        .keys()
        .filter(|key| !known.contains(&key.as_str()))
        .cloned()
        .collect();
    unknown.sort();
    if !unknown.is_empty() {
        return Err(format!("unknown kata config keys: {}", unknown.join(", ")));
    }
    for (key, fields) in [
        ("rule_exceptions", ["rule", "path", "reason"].as_slice()),
        ("rule_ignores", ["rules", "paths", "reason"].as_slice()),
        ("select_star_allow", ["paths", "reason"].as_slice()),
        (
            "threshold_overrides",
            ["paths", "thresholds", "reason"].as_slice(),
        ),
    ] {
        let Some(entries) = table.get(key).and_then(toml::Value::as_array) else {
            continue;
        };
        for entry in entries {
            let Some(entry_table) = entry.as_table() else {
                continue;
            };
            for field in fields {
                if !entry_table.contains_key(*field) {
                    return Err(format!("kata.{key}.{field} must be a non-empty value"));
                }
            }
        }
    }
    Ok(())
}

pub(crate) fn validate(config: &KataConfig) -> Result<(), String> {
    const THRESHOLDS: [&str; 10] = [
        "min_audits_per_model",
        "min_tests_per_model",
        "min_custom_rule_test_cases",
        "max_subdomain_depth",
        "min_shared_owner_prefix_directories",
        "max_role_container_depth",
        "max_macro_container_files",
        "max_constant_container_files",
        "max_enum_container_files",
        "min_shared_container_prefix_files",
    ];
    if config.layout.levels.is_empty() {
        return Err("kata.layout.levels must contain at least one normalized relative path".into());
    }
    let mut levels: std::collections::BTreeSet<&String> = std::collections::BTreeSet::new();
    for level in &config.layout.levels {
        validate_relative_path(level, "kata.layout.levels")?;
        if !levels.insert(level) {
            return Err(format!("duplicate kata layout level: {level}"));
        }
    }
    validate_non_overlapping_paths(&config.layout.levels, "kata.layout.levels")?;
    let mut domain_roots: std::collections::BTreeSet<&String> = std::collections::BTreeSet::new();
    for root in &config.layout.domain_roots {
        validate_relative_path(root, "kata.layout.domain_roots")?;
        if !domain_roots.insert(root) {
            return Err(format!("duplicate kata layout domain root: {root}"));
        }
    }
    validate_non_overlapping_paths(&config.layout.domain_roots, "kata.layout.domain_roots")?;
    let pipeline = Path::new(&config.sql_tests.pipeline_directory);
    if config.sql_tests.pipeline_directory.trim().is_empty()
        || config.sql_tests.pipeline_directory.contains('\\')
        || config.sql_tests.pipeline_directory.contains("//")
        || config.sql_tests.pipeline_directory.ends_with('/')
        || config
            .sql_tests
            .pipeline_directory
            .split('/')
            .next()
            .is_some_and(|component| component.ends_with(':'))
        || pipeline.is_absolute()
        || pipeline
            .components()
            .any(|component| !matches!(component, std::path::Component::Normal(_)))
    {
        return Err(
            "kata.sql_tests.pipeline_directory must be a normalized path relative to tests/unit"
                .into(),
        );
    }
    if let Some(name) = config
        .thresholds
        .keys()
        .find(|key| !THRESHOLDS.contains(&key.as_str()))
    {
        return Err(format!("unknown kata thresholds: {name}"));
    }
    for entry in &config.threshold_overrides {
        if entry.paths.is_empty() || entry.thresholds.is_empty() || entry.reason.trim().is_empty() {
            return Err("kata.threshold_overrides requires paths, thresholds, and reason".into());
        }
        if let Some(name) = entry
            .thresholds
            .keys()
            .find(|key| !["min_audits_per_model", "min_tests_per_model"].contains(&key.as_str()))
        {
            return Err(format!("unknown kata threshold override: {name}"));
        }
        for pattern in &entry.paths {
            if pattern.trim().is_empty() {
                return Err("kata threshold override paths must be non-empty globs".into());
            }
            globset::Glob::new(pattern).map_err(|error| {
                format!("invalid kata threshold override path {pattern}: {error}")
            })?;
        }
    }
    let grammar = ProductRuleCodeGrammar::new("SQBK", "XSQBK")?;
    for selector in config.select.iter().chain(&config.ignore) {
        if !grammar.rule_selector_is_valid(selector) {
            return Err(format!("malformed kata rule selector: {selector}"));
        }
    }
    for code in config.rule_options.keys() {
        if !grammar.rule_code_is_exact(code) {
            return Err(format!("invalid kata rule code: {code}"));
        }
    }
    for exception in &config.rule_exceptions {
        if exception.rule.trim().is_empty()
            || exception.path.trim().is_empty()
            || exception.reason.trim().is_empty()
        {
            return Err("kata.rule_exceptions fields must be non-empty strings".into());
        }
        if !grammar.rule_code_is_exact(&exception.rule) {
            return Err(format!("invalid kata rule code: {}", exception.rule));
        }
    }
    for ignore in &config.rule_ignores {
        if ignore.rules.is_empty() || ignore.paths.is_empty() || ignore.reason.trim().is_empty() {
            return Err("kata.rule_ignores requires rules, paths, and reason".into());
        }
        if let Some(selector) = ignore
            .rules
            .iter()
            .find(|selector| !grammar.rule_selector_is_valid(selector))
        {
            return Err(format!("malformed kata rule selector: {selector}"));
        }
    }
    for allow in &config.select_star_allow {
        if allow.paths.is_empty() || allow.reason.trim().is_empty() {
            return Err("kata.select_star_allow requires paths and reason".into());
        }
    }
    Ok(())
}

fn validate_relative_path(value: &str, label: &str) -> Result<(), String> {
    let path = Path::new(value);
    if value.trim().is_empty()
        || value.contains('\\')
        || value.contains("//")
        || value.ends_with('/')
        || value
            .split('/')
            .next()
            .is_some_and(|component| component.ends_with(':'))
        || path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, std::path::Component::Normal(_)))
    {
        return Err(format!(
            "{label} entries must be normalized project-relative paths"
        ));
    }
    Ok(())
}

fn validate_non_overlapping_paths(values: &[String], label: &str) -> Result<(), String> {
    for (index, left) in values.iter().enumerate() {
        for right in values.iter().skip(index + 1) {
            let left_prefix = format!("{left}/");
            let right_prefix = format!("{right}/");
            if left.starts_with(&right_prefix) || right.starts_with(&left_prefix) {
                return Err(format!("{label} entries must not overlap: {left}, {right}"));
            }
        }
    }
    Ok(())
}
