use crate::configuration::main::validate as config;
use crate::constants::{API_VERSION, TARGET_DIRECTORY};
use crate::engine::_helpers::cache::Cache;
use crate::models::{EvaluateRequest, EvaluateResponse, Fault, RuleMetadata};
use crate::rules::main::{
    assemble_catalogue, evaluate as rules, evaluate_project, fingerprint,
    resolve_threshold_overrides, select,
};
use crate::rules::models::{ModelEvaluationRequest, ProjectEvaluationRequest};
use fensu_policy::lifecycle::constants::ANALYSIS_BATCH_SCHEMA_VERSION;
use fensu_policy::lifecycle::errors::LifecycleError;
use fensu_policy::lifecycle::models::{
    AnalysisBatchRequest, AnalysisInput, ApplySuppressionsRequest, CustomHostInvocation,
    CustomHostOutputLimits, CustomHostRequest, ExactSuppression, Finding, FindingSeverity,
    RuntimeIdentity, ScopedIgnore,
};
use fensu_policy::policy::models::ProductRuleCodeGrammar;
use fensu_policy::{apply_suppressions, evaluate_batch, run_custom_host};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::time::Duration;

pub(crate) fn evaluate_json(request_json: &str) -> Result<String, String> {
    let request: EvaluateRequest = serde_json::from_str(request_json)
        .map_err(|error| format!("invalid kata request: {error}"))?;
    if request.version != API_VERSION {
        return Err(format!(
            "unsupported kata native API version {}; expected {API_VERSION}",
            request.version
        ));
    }
    config::validate(&request.config)?;
    let all_rules = assemble_catalogue::assemble_catalogue(&request.custom_rules)?;
    let selected = select::select(&all_rules, &request.config.select, &request.config.ignore)?;
    validate_suppression_codes(&request, &all_rules)?;
    let ruleset_fingerprint = fingerprint::fingerprint(&selected, &request.config)?;
    let selected_by_code: BTreeMap<String, &RuleMetadata> = selected
        .iter()
        .map(|rule| (rule.code.clone(), *rule))
        .collect();
    let custom_faults = evaluate_custom_rules(&request, &selected_by_code)?;
    let threshold_overrides =
        resolve_threshold_overrides::resolve_threshold_overrides(&request.config)?;
    if selected.is_empty() {
        validate_exception_paths(&request)?;
        let _ = suppress_faults(&request, &selected, Vec::new())?;
        return serde_json::to_string(&EvaluateResponse {
            version: API_VERSION,
            faults: Vec::new(),
            evaluated_models: 0,
            cache_hits: 0,
            cache_misses: 0,
            ruleset_fingerprint,
        })
        .map_err(|error| error.to_string());
    }

    let custom_selected = selected.iter().any(|rule| rule.custom);
    let cache_enabled = request.config.cache.enabled
        && (!custom_selected || request.config.cache.require_cacheable);
    let project_aware = selected
        .iter()
        .any(|rule| rule.project_wide || rule.code.starts_with("SQBKX") || rule.custom);
    let project_fingerprint = if project_aware {
        Some(match &request.project_fingerprint {
            Some(value) => fingerprint_request_facts(value.as_bytes(), &request)?,
            None => fingerprint_project(Path::new(&request.project_dir), &request)?,
        })
    } else {
        None
    };
    let cache = cache_enabled
        .then(|| Cache::open(Path::new(&request.project_dir)))
        .transpose()?;
    let mut models: Vec<_> = request.models.iter().collect();
    models.sort_by(|left, right| left.relative_path.cmp(&right.relative_path));
    let mut raw_faults = evaluate_project::evaluate_project(ProjectEvaluationRequest {
        selected: &selected_by_code,
        request: &request,
    })?;
    let mut cache_hits = 0;
    let mut cache_misses = 0;
    for (model_index, model) in models.iter().enumerate() {
        let fingerprint = cache
            .as_ref()
            .map(|_| {
                model_cache_identity(model, &ruleset_fingerprint, project_fingerprint.as_deref())
            })
            .transpose()?;
        if let (Some(store), Some(identity)) = (&cache, &fingerprint) {
            if let Some(cached) = store.get(&model.relative_path, identity)? {
                raw_faults.extend(cached);
                cache_hits += 1;
                continue;
            }
        }
        cache_misses += 1;
        let model_faults = rules::evaluate_model(ModelEvaluationRequest {
            model,
            config: &request.config,
            selected: &selected_by_code,
            request: &request,
            is_anchor: model_index == 0,
            threshold_overrides: &threshold_overrides,
        })?;
        if let (Some(store), Some(identity)) = (&cache, &fingerprint) {
            store.put(&model.relative_path, identity, &model_faults)?;
        }
        raw_faults.extend(model_faults);
    }
    raw_faults.extend(custom_faults);
    validate_exception_paths(&request)?;
    let faults = suppress_faults(&request, &selected, raw_faults)?;
    serde_json::to_string(&EvaluateResponse {
        version: API_VERSION,
        faults,
        evaluated_models: models.len(),
        cache_hits,
        cache_misses,
        ruleset_fingerprint,
    })
    .map_err(|error| error.to_string())
}

fn model_cache_identity(
    model: &crate::models::Model,
    ruleset: &str,
    project: Option<&str>,
) -> Result<String, String> {
    let request = AnalysisBatchRequest {
        schema_version: ANALYSIS_BATCH_SCHEMA_VERSION,
        required_capabilities: Vec::new(),
        identity: RuntimeIdentity {
            producer: "sqlbuild-kata".to_owned(),
            fact_schema: "sqlbuild-kata-model-v1".to_owned(),
            runtime: env!("CARGO_PKG_VERSION").to_owned(),
            rule_pack: ruleset.to_owned(),
            configuration: project.unwrap_or("model-local").to_owned(),
        },
        inputs: vec![AnalysisInput {
            path: model.relative_path.clone(),
            fingerprint: "compiled-model-v1".to_owned(),
            facts: model,
        }],
    };
    evaluate_batch(&request, &[], |_| Ok(Vec::new()))
        .map(|response| response.cache_identity)
        .map_err(lifecycle_error)
}

fn fingerprint_project(project_dir: &Path, request: &EvaluateRequest) -> Result<String, String> {
    let mut files = collect_policy_files(project_dir, project_dir)?;
    files.sort();
    let mut digest = Sha256::new();
    for path in files {
        let relative = path.strip_prefix(project_dir).unwrap_or(&path);
        digest.update(relative.to_string_lossy().as_bytes());
        digest.update(std::fs::read(&path).map_err(|error| {
            format!(
                "could not fingerprint kata project file {}: {error}",
                path.display()
            )
        })?);
    }
    fingerprint_request_facts(&digest.finalize(), request)
}

fn fingerprint_request_facts(seed: &[u8], request: &EvaluateRequest) -> Result<String, String> {
    let mut digest = Sha256::new();
    digest.update(seed);
    digest.update(
        serde_json::to_vec(&(
            &request.public_enums,
            &request.public_constants,
            &request.sql_tests,
            &request.sql_scenarios,
        ))
        .map_err(|error| error.to_string())?,
    );
    Ok(format!("{:x}", digest.finalize()))
}

fn collect_policy_files(root: &Path, directory: &Path) -> Result<Vec<PathBuf>, String> {
    let mut output: Vec<PathBuf> = Vec::new();
    for entry in std::fs::read_dir(directory)
        .map_err(|error| format!("could not read kata project directory: {error}"))?
    {
        let entry = entry.map_err(|error| format!("could not read kata project entry: {error}"))?;
        let path = entry.path();
        if path.is_dir() {
            if path
                .file_name()
                .is_some_and(|name| name == TARGET_DIRECTORY)
            {
                continue;
            }
            output.extend(collect_policy_files(root, &path)?);
            continue;
        }
        let supported = path
            .extension()
            .and_then(|value| value.to_str())
            .is_some_and(|value| matches!(value, "py" | "sql" | "toml" | "yaml" | "yml"));
        if supported && path.starts_with(root) {
            output.push(path);
        }
    }
    Ok(output)
}

fn validate_suppression_codes(
    request: &EvaluateRequest,
    catalogue: &[RuleMetadata],
) -> Result<(), String> {
    let codes: BTreeSet<_> = catalogue.iter().map(|rule| rule.code.as_str()).collect();
    let unknown: BTreeSet<_> = request
        .config
        .rule_exceptions
        .iter()
        .map(|entry| entry.rule.as_str())
        .filter(|code| !codes.contains(code))
        .collect();
    if !unknown.is_empty() {
        return Err(format!(
            "kata exceptions target unknown rules: {}",
            unknown.into_iter().collect::<Vec<_>>().join(", ")
        ));
    }
    for ignore in &request.config.rule_ignores {
        for selector in &ignore.rules {
            if !catalogue.iter().any(|rule| rule.code.starts_with(selector)) {
                return Err(format!(
                    "kata rule-ignore selector matches no rules: {selector}"
                ));
            }
        }
    }
    Ok(())
}

fn validate_custom_faults(
    faults: &[Fault],
    selected: &BTreeMap<String, &RuleMetadata>,
) -> Result<(), String> {
    for fault in faults {
        if !selected.get(&fault.code).is_some_and(|rule| rule.custom) {
            return Err(format!(
                "custom kata host returned a fault for unselected rule {}",
                fault.code
            ));
        }
    }
    Ok(())
}

fn evaluate_custom_rules(
    request: &EvaluateRequest,
    selected: &BTreeMap<String, &RuleMetadata>,
) -> Result<Vec<Fault>, String> {
    let custom_selected = selected.values().any(|rule| rule.custom);
    let Some(spec) = &request.custom_host else {
        return if custom_selected {
            Err("selected custom kata rules require a custom host".to_owned())
        } else {
            Ok(Vec::new())
        };
    };
    if !custom_selected {
        return Ok(Vec::new());
    }
    let mut payload = spec.payload.clone();
    let payload_object = payload
        .as_object_mut()
        .ok_or_else(|| "custom kata host payload must be an object".to_owned())?;
    payload_object.insert(
        "selected_codes".to_owned(),
        serde_json::Value::Array(
            selected
                .values()
                .filter(|rule| rule.custom)
                .map(|rule| serde_json::Value::String(rule.code.clone()))
                .collect(),
        ),
    );
    let host_request = CustomHostRequest {
        protocol: fensu_policy::lifecycle::constants::CUSTOM_HOST_PROTOCOL_VERSION,
        runtime_version: spec.runtime_version.clone(),
        payload,
    };
    let response = run_custom_host::<_, Vec<Fault>>(CustomHostInvocation {
        program: Path::new(&spec.program),
        arguments: &spec.arguments,
        timeout: Duration::from_millis(spec.timeout_millis),
        output_limits: CustomHostOutputLimits::default(),
        request: &host_request,
    })
    .map_err(lifecycle_error)?;
    let faults = response.payload.ok_or_else(|| {
        "custom kata host returned no fault payload after successful validation".to_owned()
    })?;
    validate_custom_faults(&faults, selected)?;
    Ok(faults)
}

fn validate_exception_paths(request: &EvaluateRequest) -> Result<(), String> {
    let root = Path::new(&request.project_dir);
    for entry in &request.config.rule_exceptions {
        if !root.join(&entry.path).is_file() {
            return Err(format!(
                "kata exception path does not exist: {}",
                entry.path
            ));
        }
    }
    Ok(())
}

fn suppress_faults(
    request: &EvaluateRequest,
    selected: &[&RuleMetadata],
    faults: Vec<Fault>,
) -> Result<Vec<Fault>, String> {
    let findings = faults
        .into_iter()
        .map(fault_to_finding)
        .collect::<Result<Vec<_>, _>>()?;
    let evaluated_codes = selected
        .iter()
        .map(|rule| rule.code.clone())
        .collect::<Vec<_>>();
    let suppressions = request
        .config
        .rule_exceptions
        .iter()
        .map(|entry| ExactSuppression {
            code: entry.rule.clone(),
            path: entry.path.clone(),
            symbol: None,
            reason: entry.reason.clone(),
        })
        .collect::<Vec<_>>();
    let scoped_ignores = request
        .config
        .rule_ignores
        .iter()
        .map(|entry| ScopedIgnore {
            selectors: entry.rules.clone(),
            paths: entry.paths.clone(),
            reason: entry.reason.clone(),
        })
        .collect::<Vec<_>>();
    let grammar = ProductRuleCodeGrammar::new("SQBK", "XSQBK")?;
    apply_suppressions(ApplySuppressionsRequest {
        findings,
        evaluated_codes: &evaluated_codes,
        suppressions: &suppressions,
        scoped_ignores: &scoped_ignores,
        grammar: &grammar,
    })
    .map(|result| result.findings.into_iter().map(finding_to_fault).collect())
    .map_err(lifecycle_error)
}

fn fault_to_finding(fault: Fault) -> Result<Finding, String> {
    Ok(Finding {
        code: fault.code,
        path: fault.path,
        line: Some(u32::try_from(fault.line).map_err(|_| "kata fault line exceeds u32")?),
        column: Some(u32::try_from(fault.column).map_err(|_| "kata fault column exceeds u32")?),
        symbol: None,
        message: fault.message,
        remediation: Some(fault.remediation),
        severity: FindingSeverity::Blocking,
    })
}

fn finding_to_fault(finding: Finding) -> Fault {
    Fault {
        code: finding.code,
        path: finding.path,
        line: u64::from(finding.line.unwrap_or(1)),
        column: u64::from(finding.column.unwrap_or(1)),
        message: finding.message,
        remediation: finding.remediation.unwrap_or_default(),
    }
}

fn lifecycle_error(error: LifecycleError) -> String {
    match error {
        LifecycleError::StaleSuppression { code, path, .. } => {
            format!("stale kata exception suppresses no fault: {code} at {path}")
        }
        other => format!("invalid kata lifecycle: {other}"),
    }
}
