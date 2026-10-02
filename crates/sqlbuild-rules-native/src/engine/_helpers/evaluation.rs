use crate::configuration::main::validate as config;
use crate::constants::{API_VERSION, NATIVE_BUILD_IDENTITY};
use crate::engine::_helpers::cache::{Cache, RuleCacheEntry};
use crate::models::{
    EvaluateRequest, EvaluateResponse, Fault, Model, RuleMetadata, RulesCodeGrammar,
};
use crate::rules::main::{
    assemble_catalogue, evaluate as rules, evaluate_project, fingerprint,
    resolve_threshold_overrides, select, sql_test_coverage,
};
use crate::rules::models::{
    ModelEvaluationRequest, ProjectEvaluationRequest, ResolvedThresholdOverride,
};
use fensu_policy::lifecycle::constants::ANALYSIS_BATCH_SCHEMA_VERSION;
use fensu_policy::lifecycle::errors::LifecycleError;
use fensu_policy::lifecycle::models::{
    AnalysisBatchRequest, AnalysisInput, ApplySuppressionsRequest, ExactSuppression, Finding,
    FindingSeverity, RuntimeIdentity, ScopedIgnore,
};
use fensu_policy::{apply_suppressions, evaluate_batch};
use rayon::iter::{
    IndexedParallelIterator, IntoParallelIterator, IntoParallelRefIterator, ParallelIterator,
};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::time::Instant;

const NATIVE_RULE_WORKERS: usize = 4;
const NATIVE_RULE_STACK_BYTES: usize = 16 * 1024 * 1024;
const COMPILER_FACTS_FINGERPRINT_SEED: &str = "compiler-owned-rules-facts-v2";

struct PendingModelRule<'a> {
    index: usize,
    model: &'a Model,
    identity: Option<String>,
}

struct CompletedModelRule {
    index: usize,
    identity: Option<String>,
    faults: Result<Vec<Fault>, String>,
}

struct ModelRuleBatchContext<'a> {
    request: &'a EvaluateRequest,
    selected: &'a BTreeMap<String, &'a RuleMetadata>,
    threshold_overrides: &'a [ResolvedThresholdOverride],
}

struct NativeModelRuleRequest<'a> {
    context: ModelRuleBatchContext<'a>,
    cache: Option<&'a Cache>,
    ruleset_fingerprint: &'a str,
    project_fingerprint: Option<&'a str>,
}

#[derive(Default)]
struct NativeModelEvaluation {
    faults: Vec<Fault>,
    hits: usize,
    misses: usize,
}

fn evaluate_native_models(
    input: NativeModelRuleRequest<'_>,
) -> Result<NativeModelEvaluation, String> {
    let NativeModelRuleRequest {
        context,
        cache,
        ruleset_fingerprint,
        project_fingerprint,
    } = input;
    if !context
        .selected
        .values()
        .any(|rule| !rule.custom && !rule.code.starts_with("SQBRSQL"))
    {
        return Ok(NativeModelEvaluation::default());
    }
    let mut models: Vec<_> = context.request.models.iter().collect();
    models.sort_by(|left, right| left.relative_path.cmp(&right.relative_path));
    let all_models_required = context.selected.values().any(|rule| {
        !rule.custom
            && !rule.code.starts_with("SQBRSQL")
            && !matches!(
                rule.code.as_str(),
                "SQBRDECLARATION201" | "SQBRDECLARATION301" | "SQBRTEST301"
            )
    });
    let model_limit = if all_models_required { models.len() } else { 1 };
    let mut bucket = cache
        .map(|store| store.native_rules_bucket(ruleset_fingerprint))
        .transpose()?
        .unwrap_or_default();
    let mut bucket_changed = false;
    let mut result = NativeModelEvaluation::default();
    let mut model_results: Vec<Option<Vec<Fault>>> = vec![None; model_limit];
    let mut pending_models: Vec<PendingModelRule<'_>> = Vec::new();
    let mut identities = if cache.is_some() {
        model_cache_identities(
            &models[..model_limit],
            ruleset_fingerprint,
            project_fingerprint,
        )?
        .into_iter()
        .map(Some)
        .collect()
    } else {
        vec![None; model_limit]
    };
    for (index, model) in models.iter().take(model_limit).enumerate() {
        let identity = identities[index].take();
        if let Some(identity) = &identity
            && let Some(entry) = bucket
                .entries
                .get(&model.relative_path)
                .filter(|entry| entry.identity == *identity)
        {
            model_results[index] = Some(entry.faults.clone());
            result.hits += 1;
            continue;
        }
        result.misses += 1;
        pending_models.push(PendingModelRule {
            index,
            model,
            identity,
        });
    }
    let completed = evaluate_pending_models(pending_models, context)?;
    for completed_model in completed {
        let faults = completed_model.faults?;
        if let Some(identity) = completed_model.identity {
            let _ = bucket.entries.insert(
                models[completed_model.index].relative_path.clone(),
                RuleCacheEntry {
                    identity,
                    faults: faults.clone(),
                },
            );
            bucket_changed = true;
        }
        model_results[completed_model.index] = Some(faults);
    }
    result.faults = model_results.into_iter().flatten().flatten().collect();
    if bucket_changed && let Some(cache) = cache {
        cache.put_native_rules_bucket(ruleset_fingerprint, &bucket)?;
    }
    Ok(result)
}

fn evaluate_pending_models(
    pending_models: Vec<PendingModelRule<'_>>,
    context: ModelRuleBatchContext<'_>,
) -> Result<Vec<CompletedModelRule>, String> {
    let evaluate_pending = |pending: PendingModelRule<'_>| CompletedModelRule {
        index: pending.index,
        identity: pending.identity,
        faults: rules::evaluate_model(ModelEvaluationRequest {
            model: pending.model,
            config: &context.request.config,
            selected: context.selected,
            request: context.request,
            threshold_overrides: context.threshold_overrides,
        }),
    };
    if pending_models.len() <= 1 {
        return Ok(pending_models.into_iter().map(evaluate_pending).collect());
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(NATIVE_RULE_WORKERS.min(pending_models.len()))
        .stack_size(NATIVE_RULE_STACK_BYTES)
        .build()
        .map_err(|error| error.to_string())?;
    Ok(pool.install(|| {
        pending_models
            .into_par_iter()
            .map(evaluate_pending)
            .collect()
    }))
}

pub(crate) fn evaluate_json(request_json: &str) -> Result<String, String> {
    let request: EvaluateRequest = serde_json::from_str(request_json)
        .map_err(|error| format!("invalid rules request: {error}"))?;
    if request.version != API_VERSION {
        return Err(format!(
            "unsupported rules native API version {}; expected {API_VERSION}",
            request.version
        ));
    }
    config::validate(&request.config)?;
    let all_rules = assemble_catalogue::assemble_catalogue(&request.custom_rules)?;
    let selected = select::select(&all_rules, &request.config.select, &request.config.ignore)?;
    let request = if selected
        .iter()
        .any(|rule| matches!(rule.code.as_str(), "SQBRTEST202" | "SQBRTEST203"))
    {
        sql_test_coverage::annotate(request)
    } else {
        request
    };
    validate_suppression_codes(&request, &all_rules)?;
    let ruleset_fingerprint =
        fingerprint::fingerprint(&selected, &request.config, &request.dialect)?;
    let selected_by_code: BTreeMap<String, &RuleMetadata> = selected
        .iter()
        .map(|rule| (rule.code.clone(), *rule))
        .collect();
    let threshold_overrides =
        resolve_threshold_overrides::resolve_threshold_overrides(&request.config)?;
    if selected.is_empty() {
        validate_exception_paths(&request)?;
        if !request.defer_suppressions {
            let _ = suppress_faults(&request, &selected, Vec::new())?;
        }
        return serde_json::to_string(&EvaluateResponse {
            version: API_VERSION,
            faults: Vec::new(),
            evaluated_models: 0,
            cache_hits: 0,
            cache_misses: 0,
            ruleset_fingerprint,
            selected_codes: Vec::new(),
            built_in_ms: 0,
        })
        .map_err(|error| error.to_string());
    }

    let cache_enabled = request.config.cache.enabled;
    let project_aware = selected.iter().any(|rule| rule.project_wide || rule.custom);
    let project_fingerprint = project_aware
        .then(|| {
            fingerprint_request_facts(
                request
                    .project_fingerprint
                    .as_deref()
                    .unwrap_or(COMPILER_FACTS_FINGERPRINT_SEED)
                    .as_bytes(),
                &request,
            )
        })
        .transpose()?;
    let cache = cache_enabled
        .then(|| Cache::open(Path::new(&request.project_dir)))
        .transpose()?;
    let built_in_started = Instant::now();
    let mut raw_faults = request.initial_findings.clone();
    raw_faults.extend(evaluate_project::evaluate_project(
        ProjectEvaluationRequest {
            selected: &selected_by_code,
            request: &request,
        },
    )?);
    let native = evaluate_native_models(NativeModelRuleRequest {
        context: ModelRuleBatchContext {
            request: &request,
            selected: &selected_by_code,
            threshold_overrides: &threshold_overrides,
        },
        cache: cache.as_ref(),
        ruleset_fingerprint: &ruleset_fingerprint,
        project_fingerprint: project_fingerprint.as_deref(),
    })?;
    let cache_hits = native.hits;
    let cache_misses = native.misses;
    raw_faults.extend(native.faults);
    let built_in_ms = built_in_started.elapsed().as_millis() as u64;
    validate_exception_paths(&request)?;
    let faults = if request.defer_suppressions {
        raw_faults
    } else {
        suppress_faults(&request, &selected, raw_faults)?
    };
    serde_json::to_string(&EvaluateResponse {
        version: API_VERSION,
        faults,
        evaluated_models: request.models.len(),
        cache_hits,
        cache_misses,
        ruleset_fingerprint,
        selected_codes: selected.iter().map(|rule| rule.code.clone()).collect(),
        built_in_ms,
    })
    .map_err(|error| error.to_string())
}

fn model_cache_identities(
    models: &[&crate::models::Model],
    ruleset: &str,
    project: Option<&str>,
) -> Result<Vec<String>, String> {
    let identity = |(index, model): (usize, &&crate::models::Model)| {
        model_cache_identity(model, ruleset, if index == 0 { project } else { None })
    };
    let results: Vec<Result<String, String>> = if models.len() <= 1 {
        models.iter().enumerate().map(identity).collect()
    } else {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(NATIVE_RULE_WORKERS.min(models.len()))
            .stack_size(NATIVE_RULE_STACK_BYTES)
            .build()
            .map_err(|error| error.to_string())?;
        pool.install(|| models.par_iter().enumerate().map(identity).collect())
    };
    results.into_iter().collect()
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
            producer: "sqlbuild-rules".to_owned(),
            fact_schema: "sqlbuild-rules-model-v1".to_owned(),
            runtime: NATIVE_BUILD_IDENTITY.to_owned(),
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

fn fingerprint_request_facts(seed: &[u8], request: &EvaluateRequest) -> Result<String, String> {
    let mut digest = Sha256::new();
    digest.update(seed);
    digest.update(
        serde_json::to_vec(&(
            &request.models,
            &request.public_enums,
            &request.public_constants,
            &request.sql_tests,
            &request.sql_scenarios,
            &request.scope_index,
            &request.custom_rules,
        ))
        .map_err(|error| error.to_string())?,
    );
    Ok(format!("{:x}", digest.finalize()))
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
            "rule exceptions target unknown rules: {}",
            unknown.into_iter().collect::<Vec<_>>().join(", ")
        ));
    }
    for ignore in &request.config.rule_ignores {
        for selector in &ignore.rules {
            if !catalogue.iter().any(|rule| rule.code.starts_with(selector)) {
                return Err(format!("rule-ignore selector matches no rules: {selector}"));
            }
        }
    }
    Ok(())
}

fn validate_exception_paths(request: &EvaluateRequest) -> Result<(), String> {
    let root = Path::new(&request.project_dir);
    for entry in &request.config.rule_exceptions {
        if !root.join(&entry.path).is_file() {
            return Err(format!(
                "rule exception path does not exist: {}",
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
    let evaluated_codes = selected
        .iter()
        .map(|rule| rule.code.clone())
        .collect::<Vec<_>>();
    apply_fault_policy(request, &evaluated_codes, faults)
}

pub(crate) fn finalize_findings_json(request_json: &str) -> Result<String, String> {
    let input: crate::models::FinalizeFindingsRequest = serde_json::from_str(request_json)
        .map_err(|error| format!("invalid findings request: {error}"))?;
    if input.version != API_VERSION {
        return Err(format!(
            "unsupported rules native API version {}; expected {API_VERSION}",
            input.version
        ));
    }
    config::validate(&input.config)?;
    let request = EvaluateRequest {
        project_dir: input.project_dir,
        config: input.config,
        ..Default::default()
    };
    validate_exception_paths(&request)?;
    let faults = apply_fault_policy(&request, &input.evaluated_codes, input.findings)?;
    serde_json::to_string(&faults).map_err(|error| error.to_string())
}

fn apply_fault_policy(
    request: &EvaluateRequest,
    evaluated_codes: &[String],
    faults: Vec<Fault>,
) -> Result<Vec<Fault>, String> {
    let unevaluated: BTreeSet<_> = faults
        .iter()
        .filter(|fault| fault.unevaluated)
        .map(|fault| {
            (
                fault.code.clone(),
                fault.path.clone(),
                fault.message.clone(),
            )
        })
        .collect();
    let findings = faults
        .into_iter()
        .map(fault_to_finding)
        .collect::<Result<Vec<_>, _>>()?;
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
    let grammar = RulesCodeGrammar;
    let result = apply_suppressions(ApplySuppressionsRequest {
        findings,
        evaluated_codes,
        suppressions: &suppressions,
        scoped_ignores: &scoped_ignores,
        grammar: &grammar,
    })
    .map_err(lifecycle_error)?;
    Ok(result
        .findings
        .into_iter()
        .map(|finding| {
            let mut fault = finding_to_fault(finding);
            fault.unevaluated = unevaluated.contains(&(
                fault.code.clone(),
                fault.path.clone(),
                fault.message.clone(),
            ));
            fault
        })
        .collect())
}

fn fault_to_finding(fault: Fault) -> Result<Finding, String> {
    Ok(Finding {
        code: fault.code,
        path: fault.path,
        line: Some(u32::try_from(fault.line).map_err(|_| "rule finding line exceeds u32")?),
        column: Some(u32::try_from(fault.column).map_err(|_| "rule finding column exceeds u32")?),
        symbol: None,
        message: fault.message,
        remediation: Some(fault.remediation),
        severity: FindingSeverity::Blocking,
    })
}

fn finding_to_fault(finding: Finding) -> Fault {
    Fault {
        unevaluated: false,
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
            format!("stale rule exception suppresses no finding: {code} at {path}")
        }
        other => format!("invalid rules lifecycle: {other}"),
    }
}
