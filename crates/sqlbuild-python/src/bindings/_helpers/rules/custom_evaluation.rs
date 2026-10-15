//! Incremental custom-rule evaluation keyed on the compiler facts each invocation read.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::PathBuf;
use std::time::Instant;

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_cache::digest::main::sha256_hex::sha256_hex;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, OrjsonOptions};
use sqlbuild_rules::custom_host_pool::models::{HostRuleSubject, HostRun};
use sqlbuild_rules::custom_host_pool::types::{FactKey, HostPlan};
use sqlbuild_rules::custom_rule_cache::models::CustomEvaluation;
use sqlbuild_rules::custom_rule_cache::types::ReadSet;

use crate::bindings::_helpers::cache::native_store::current_code_identity;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::rules::custom_hosts::{
    HostCancel, HostRequest, host_payload_project, run_custom_hosts,
};
use crate::bindings::_helpers::rules::custom_rule_cache::CustomRuleCache;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const RULES_CONSTANTS_MODULE: &str = "sqlbuild.rule_engine.constants";
const RULES_ERRORS_MODULE: &str = "sqlbuild._native";
const RULE_CONTEXT_MODULE: &str = "sqlbuild.rule_engine.classes.rule_context";
const FACT_REPLAY_MODULE: &str = "sqlbuild.rule_engine._helpers.engine.fact_replay";
const SCOPE_MODELS_MODULE: &str = "sqlbuild._native";
const PROJECT_SUBJECT: &str = "project";
const MODEL_SUBJECT: &str = "model";
/// Project fields no rule fact reads, cleared before digests and host payloads use the project.
const HOST_PROJECT_CLEARED: [(&str, Cleared); 11] = [
    ("binding_catalog", Cleared::None),
    ("sql_expansions", Cleared::Dict),
    ("loaded_macros", Cleared::Dict),
    ("loader_functions", Cleared::Tuple),
    ("hook_functions", Cleared::Tuple),
    ("materialization_files", Cleared::Tuple),
    ("external_sql_reference_resolver", Cleared::None),
    ("sql_scenarios", Cleared::Tuple),
    ("sql_hook_files", Cleared::Tuple),
    ("diagnostics", Cleared::Tuple),
    ("unmatched_literal_sql_relations", Cleared::Tuple),
];

/// The empty value one cleared project field takes.
#[derive(Clone, Copy)]
enum Cleared {
    None,
    Dict,
    Tuple,
}

/// The run one custom-rule evaluation describes.
pub(crate) struct CustomRun<'a, 'py> {
    pub(crate) project: &'a Bound<'py, PyAny>,
    pub(crate) config: &'a Bound<'py, PyAny>,
    pub(crate) project_dir: &'a Bound<'py, PyAny>,
    pub(crate) rules: Vec<Bound<'py, PyAny>>,
    pub(crate) dialect: &'a str,
    pub(crate) verify_determinism: bool,
    pub(crate) implementation_fingerprints: HashMap<String, String>,
    pub(crate) cancel: HostCancel,
}

/// Reuse results whose recorded fact reads are unchanged and evaluate only the rest.
pub(crate) fn evaluate_custom_rules_cached<'py>(
    run: CustomRun<'_, 'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = run.project.py();
    let started: Instant = Instant::now();
    let started_cpu: f64 = cpu_seconds(py)?;
    let mut custom: Vec<(String, Bound<'py, PyAny>)> = run
        .rules
        .iter()
        .map(|rule| Ok((rule.getattr("code")?.extract::<String>()?, rule.clone())))
        .collect::<PyResult<_>>()?;
    custom.sort_by(|left, right| left.0.cmp(&right.0));
    if custom.is_empty() {
        return outcome(py, (Vec::new(), 0, 0), (0, 0));
    }
    let facts_project: Bound<'py, PyAny> = host_project(run.project)?;
    let enabled: bool = run
        .config
        .getattr("cache")?
        .getattr("enabled")?
        .is_truthy()?;
    let mut rows: Vec<(String, Option<String>, Option<String>)> = Vec::new();
    for (code, rule) in &custom {
        let identity: Option<String> = if enabled {
            Some(rule_identity(
                &run,
                rule,
                run.implementation_fingerprints.get(code),
            )?)
        } else {
            None
        };
        rows.push((code.clone(), identity, subject_value(rule)?));
    }
    let cache_path: Option<PathBuf> = if enabled {
        Some(
            call_with(
                &imported(py, NATIVE_MODULE, "rules_bulk_cache_path")?,
                &[
                    ("project_dir", run.project_dir.clone()),
                    (
                        "file_name",
                        imported(py, RULES_CONSTANTS_MODULE, "CUSTOM_RULES_CACHE_FILE")?,
                    ),
                ],
            )?
            .extract()?,
        )
    } else {
        None
    };
    let mut cache: CustomRuleCache = CustomRuleCache::new(
        cache_path,
        rows,
        run.project.getattr("effective_target_name")?.extract()?,
        model_rows(run.project)?,
    );
    let mut digests: FactDigests<'py> =
        FactDigests::new(&facts_project, run.project_dir, run.dialect)?;
    let pending: Vec<ReadSet> = cache.pending_readsets().to_vec();
    let mut readset_digests: Vec<Option<String>> = Vec::new();
    for readset in &pending {
        readset_digests.push(digests.reproducible(|digests| digests.combined(readset))?);
    }
    let plan: HostPlan = cache.plan(readset_digests);
    if !plan.is_empty() {
        let rules: Vec<(String, HostRuleSubject)> = custom
            .iter()
            .map(|(code, rule)| Ok((code.clone(), host_subject(rule)?)))
            .collect::<PyResult<_>>()?;
        let mut model_paths: Vec<String> = model_rows(run.project)?
            .into_iter()
            .map(|(path, _, _)| path)
            .collect();
        model_paths.sort();
        let project_dir: PathBuf = run.project_dir.extract()?;
        let host_run: HostRun = run_custom_hosts(
            py,
            &HostRequest {
                project: &facts_project,
                config: run.config,
                project_dir: &project_dir,
                dialect: run.dialect,
                rules: &rules,
                model_paths: &model_paths,
                track_reads: enabled,
                verify_determinism: run.verify_determinism,
                cancel: &run.cancel,
            },
            &plan,
        )?;
        let evaluations: Vec<CustomEvaluation> = evaluations(host_run, &mut digests, enabled)?;
        cache.record(py, evaluations)?;
    }
    let elapsed_ms: i64 = (started.elapsed().as_secs_f64() * 1000.0).round_ties_even() as i64;
    let cpu_ms: i64 = ((cpu_seconds(py)? - started_cpu) * 1000.0) as i64;
    outcome(
        py,
        (cache.findings(py)?, cache.hits(), cache.misses()),
        (elapsed_ms, cpu_ms),
    )
}

/// `CustomRulesOutcome(findings=..., cache_hits=..., cache_misses=..., custom_ms=..., ...)`.
pub(crate) fn outcome<'py>(
    py: Python<'py>,
    (findings, hits, misses): (Vec<Bound<'py, PyAny>>, usize, usize),
    (custom_ms, custom_cpu_ms): (i64, i64),
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "CustomRulesOutcome")?,
        &[
            ("findings", PyTuple::new(py, findings)?.into_any()),
            ("cache_hits", hits.into_bound_py_any(py)?),
            ("cache_misses", misses.into_bound_py_any(py)?),
            ("custom_ms", custom_ms.into_bound_py_any(py)?),
            ("custom_cpu_ms", custom_cpu_ms.into_bound_py_any(py)?),
        ],
    )
}

/// Each evaluated invocation with its read set and its digest when it may be cached.
fn evaluations(
    run: HostRun,
    digests: &mut FactDigests<'_>,
    cacheable: bool,
) -> PyResult<Vec<CustomEvaluation>> {
    let mut full_keys: Option<Vec<FactKey>> = None;
    let mut combined: HashMap<ReadSet, Option<String>> = HashMap::new();
    let mut rows: Vec<CustomEvaluation> = Vec::new();
    for evaluation in run.evaluated {
        let mut stored: Option<(ReadSet, Option<String>)> = None;
        if cacheable && !run.uncacheable.contains(&evaluation.code) {
            let reads: Vec<FactKey> = match evaluation.reads {
                Some(reads) => reads,
                None => {
                    if full_keys.is_none() {
                        full_keys = Some(digests.full_fact_keys()?);
                    }
                    let mut reads: Vec<FactKey> = run
                        .untracked_reads
                        .get(&evaluation.code)
                        .cloned()
                        .unwrap_or_default();
                    reads.extend(full_keys.iter().flatten().cloned());
                    reads
                }
            };
            let readset: ReadSet = reads
                .into_iter()
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect();
            if !combined.contains_key(&readset) {
                let digest: Option<String> = digests
                    .reproducible(|digests| digests.observed(&readset, &run.observed))?
                    .flatten();
                combined.insert(readset.clone(), digest);
            }
            let digest: Option<String> = combined.get(&readset).cloned().flatten();
            stored = Some((readset, digest));
        }
        rows.push(CustomEvaluation {
            code: evaluation.code,
            subject: evaluation.subject,
            cacheable: stored,
            findings: evaluation.findings,
        });
    }
    Ok(rows)
}

/// Memoized digests of recorded fact keys against one compiled project snapshot.
struct FactDigests<'py> {
    project: Bound<'py, PyAny>,
    project_dir: Bound<'py, PyAny>,
    dialect: String,
    views: Option<Bound<'py, PyAny>>,
    shared: Bound<'py, PyAny>,
    digests: HashMap<FactKey, String>,
}

impl<'py> FactDigests<'py> {
    fn new(
        project: &Bound<'py, PyAny>,
        project_dir: &Bound<'py, PyAny>,
        dialect: &str,
    ) -> PyResult<Self> {
        Ok(Self {
            project: project.clone(),
            project_dir: project_dir.clone(),
            dialect: dialect.to_owned(),
            views: None,
            shared: imported(project.py(), FACT_REPLAY_MODULE, "shared_fact_encoder")?.call0()?,
            digests: HashMap::new(),
        })
    }

    fn views(&mut self) -> PyResult<Bound<'py, PyAny>> {
        if let Some(views) = &self.views {
            return Ok(views.clone());
        }
        let py: Python<'py> = self.project.py();
        let views: Bound<'py, PyAny> = call_with(
            &imported(py, RULE_CONTEXT_MODULE, "build_rule_fact_views")?,
            &[
                ("project", self.project.clone()),
                ("project_dir", self.project_dir.clone()),
                ("dialect", self.dialect.clone().into_bound_py_any(py)?),
            ],
        )?;
        self.views = Some(views.clone());
        Ok(views)
    }

    /// One fact digest; raises `FactDigestError` when it cannot be reproduced.
    fn digest(&mut self, key: &FactKey) -> PyResult<String> {
        if let Some(cached) = self.digests.get(key) {
            return Ok(cached.clone());
        }
        let py: Python<'py> = self.project.py();
        let views: Bound<'py, PyAny> = self.views()?;
        let digest: String = call_with(
            &imported(py, FACT_REPLAY_MODULE, "fact_outcome_digest")?,
            &[
                ("views", views),
                ("key", PyTuple::new(py, key)?.into_any()),
                ("shared", self.shared.clone()),
            ],
        )?
        .extract()?;
        self.digests.insert(key.clone(), digest.clone());
        Ok(digest)
    }

    /// One read set's digest over its keys in canonical order.
    fn combined(&mut self, keys: &[FactKey]) -> PyResult<String> {
        let mut sorted: Vec<&FactKey> = keys.iter().collect();
        sorted.sort();
        let mut bytes: Vec<u8> = Vec::new();
        for key in sorted {
            bytes.extend(orjson_key(key).into_bytes());
            bytes.extend(self.digest(key)?.into_bytes());
        }
        Ok(sha256_hex(&bytes))
    }

    /// The read set's digest, or `None` when a filesystem fact changed since the rule read it.
    fn observed(
        &mut self,
        readset: &[FactKey],
        observed: &BTreeMap<FactKey, Option<String>>,
    ) -> PyResult<Option<String>> {
        let py: Python<'py> = self.project.py();
        let is_tree_fact: Bound<'py, PyAny> = imported(py, FACT_REPLAY_MODULE, "is_tree_fact")?;
        for key in readset {
            if is_tree_fact.call1((PyTuple::new(py, key)?,))?.is_truthy()?
                && let Some(seen) = observed.get(key)
                && seen.as_deref() != Some(self.digest(key)?.as_str())
            {
                return Ok(None);
            }
        }
        self.combined(readset).map(Some)
    }

    /// Keys covering every fact a custom rule can observe through its context.
    fn full_fact_keys(&mut self) -> PyResult<Vec<FactKey>> {
        let py: Python<'py> = self.project.py();
        imported(py, FACT_REPLAY_MODULE, "full_fact_keys")?
            .call1((self.views()?,))?
            .extract()
    }

    /// `body`'s value, or `None` when it raised `FactDigestError`.
    fn reproducible<T>(
        &mut self,
        body: impl FnOnce(&mut Self) -> PyResult<T>,
    ) -> PyResult<Option<T>> {
        let py: Python<'py> = self.project.py();
        match body(self) {
            Ok(value) => Ok(Some(value)),
            Err(error) if fact_digest_error(py, &error)? => Ok(None),
            Err(error) => Err(error),
        }
    }
}

fn fact_digest_error(py: Python<'_>, error: &PyErr) -> PyResult<bool> {
    let class: Bound<'_, PyAny> = imported(py, RULES_ERRORS_MODULE, "FactDigestError")?;
    error.value(py).is_instance(&class)
}

/// `orjson.dumps(key)` of one fact key.
fn orjson_key(key: &FactKey) -> String {
    let value: JsonValue = JsonValue::Array(
        key.iter()
            .map(|part| JsonValue::String(part.clone()))
            .collect(),
    );
    dumps(&value, &JsonDialect::Orjson(OrjsonOptions::default())).unwrap_or_default()
}

/// The project without state no rule fact reads, before digests and host payloads use it.
fn host_project<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("include_sql_expansions", false)?;
    let record: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "compiled_project_record")?.call((project,), Some(&options))?;
    let changes: Bound<'py, PyDict> = PyDict::new(py);
    for (name, cleared) in HOST_PROJECT_CLEARED {
        match cleared {
            Cleared::None => changes.set_item(name, py.None())?,
            Cleared::Dict => changes.set_item(name, PyDict::new(py))?,
            Cleared::Tuple => changes.set_item(name, PyTuple::empty(py))?,
        }
    }
    changes.set_item(
        "scope_index",
        imported(py, SCOPE_MODELS_MODULE, "ScopeIndex")?.call0()?,
    )?;
    imported(py, "dataclasses", "replace")?.call((record,), Some(&changes))
}

/// `(relative path, name, materialization)` of each compiled model, in project order.
fn model_rows(project: &Bound<'_, PyAny>) -> PyResult<Vec<(String, String, Option<String>)>> {
    let mut rows: Vec<(String, String, Option<String>)> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        let model: Bound<'_, PyAny> = model?;
        let materialized: Bound<'_, PyAny> = model
            .getattr("config")?
            .getattr("values")?
            .call_method1("get", ("materialized",))?;
        rows.push((
            model
                .getattr("relative_path")?
                .call_method0("as_posix")?
                .extract()?,
            model.getattr("name")?.extract()?,
            if materialized.is_instance_of::<pyo3::types::PyString>() {
                Some(materialized.extract::<String>()?)
            } else {
                None
            },
        ));
    }
    Ok(rows)
}

fn subject_value(rule: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    let subject: Bound<'_, PyAny> = rule.getattr("subject")?;
    if subject.is_none() {
        return Ok(None);
    }
    subject.getattr("value")?.extract()
}

fn host_subject(rule: &Bound<'_, PyAny>) -> PyResult<HostRuleSubject> {
    Ok(match subject_value(rule)?.as_deref() {
        Some(PROJECT_SUBJECT) => HostRuleSubject::Project,
        Some(MODEL_SUBJECT) => HostRuleSubject::Model,
        Some(_) | None => HostRuleSubject::Other,
    })
}

fn rule_identity(
    run: &CustomRun<'_, '_>,
    rule: &Bound<'_, PyAny>,
    fingerprint: Option<&String>,
) -> PyResult<String> {
    let py: Python<'_> = rule.py();
    let fingerprint: Bound<'_, PyAny> = match fingerprint {
        Some(fingerprint) => fingerprint.into_bound_py_any(py)?,
        None => {
            let closure: Bound<'_, PyAny> = call_with(
                &imported(py, NATIVE_MODULE, "custom_rule_import_closure")?,
                &[
                    ("rule", rule.clone()),
                    ("project_dir", run.project_dir.clone()),
                ],
            )?;
            call_with(
                &imported(py, NATIVE_MODULE, "custom_rule_implementation_fingerprint")?,
                &[
                    ("rule", rule.clone()),
                    ("project_dir", run.project_dir.clone()),
                    ("import_closure", closure),
                ],
            )?
        }
    };
    let subject: Option<String> = subject_value(rule)?;
    call_with(
        &imported(py, NATIVE_MODULE, "custom_rule_identity")?,
        &[
            (
                "code_identity",
                current_code_identity(py)?.into_bound_py_any(py)?,
            ),
            (
                "runtime_version",
                imported(py, RULES_CONSTANTS_MODULE, "CUSTOM_HOST_RUNTIME_VERSION")?,
            ),
            ("code", rule.getattr("code")?),
            ("family", rule.getattr("family")?),
            ("slug", rule.getattr("slug")?),
            ("message", rule.getattr("message")?),
            ("remediation", rule.getattr("remediation")?),
            ("subject", subject.into_bound_py_any(py)?),
            ("implementation_fingerprint", fingerprint),
            ("config", run.config.clone()),
            ("dialect", run.dialect.into_bound_py_any(py)?),
            (
                "project_dir",
                run.project_dir.call_method0("resolve")?.str()?.into_any(),
            ),
        ],
    )?
    .extract()
}

/// This thread's CPU plus that of finished child processes, which run the rule hosts.
fn cpu_seconds(py: Python<'_>) -> PyResult<f64> {
    let thread: f64 = imported(py, "time", "thread_time")?.call0()?.extract()?;
    let times: Bound<'_, PyAny> = imported(py, "os", "times")?.call0()?;
    let user: f64 = times.getattr("children_user")?.extract()?;
    let system: f64 = times.getattr("children_system")?.extract()?;
    Ok(thread + user + system)
}

/// The project every custom-rule host decodes from its payload.
#[pyfunction]
fn custom_host_payload<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    host_payload_project(&host_project(project)?)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(custom_host_payload, module)?)
}
