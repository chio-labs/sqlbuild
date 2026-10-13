//! Custom-rule result cache identities, read-set lookup, result merging and the cache file.

use std::collections::BTreeMap;
use std::path::PathBuf;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyTuple};
use pyo3::{IntoPyObjectExt, Py, pyclass, pyfunction, pymethods, wrap_pyfunction};
use serde_json::Value;
use sqlbuild_rules::custom_rule_cache::main::custom_rule_cache_text::custom_rule_cache_text;
use sqlbuild_rules::custom_rule_cache::main::lookup_custom_rule_cache::lookup_custom_rule_cache;
use sqlbuild_rules::custom_rule_cache::main::ordered_custom_findings::ordered_custom_findings;
use sqlbuild_rules::custom_rule_cache::main::parse_custom_rule_cache::parse_custom_rule_cache;
use sqlbuild_rules::custom_rule_cache::main::pending_readsets::pending_readsets;
use sqlbuild_rules::custom_rule_cache::main::rule_identity::rule_identity;
use sqlbuild_rules::custom_rule_cache::main::rule_subjects::rule_subjects;
use sqlbuild_rules::custom_rule_cache::main::store_custom_results::store_custom_results;
use sqlbuild_rules::custom_rule_cache::main::validate_custom_findings::validate_custom_findings;
use sqlbuild_rules::custom_rule_cache::models::{
    CustomCacheLookup, CustomEvaluation, CustomRule, ModelSubjectInput, RuleIdentityInput,
    SubjectsInput,
};
use sqlbuild_rules::custom_rule_cache::types::{ReadSet, StoredRules, SubjectResults};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compiled_project::values::plain_value;

const RULES_ERRORS_MODULE: &str = "sqlbuild.rule_engine.exceptions";
const RULES_ERROR: &str = "RulesError";

/// `(code, subject, (read set, digest) or None, findings)` of one evaluated invocation.
type EvaluationPy<'py> = (
    String,
    String,
    Option<(ReadSet, Option<String>)>,
    Vec<Bound<'py, PyAny>>,
);

/// One custom rule's cache identity from its metadata, source fingerprint and settings.
#[pyfunction]
#[pyo3(signature = (**request))]
fn custom_rule_identity(request: Option<&Bound<'_, PyDict>>) -> PyResult<String> {
    let request = Request::new("custom_rule_identity", request)?;
    Ok(rule_identity(&RuleIdentityInput {
        code_identity: request.get("code_identity")?.extract()?,
        runtime_version: request.get("runtime_version")?.extract()?,
        code: request.get("code")?.extract()?,
        family: request.get("family")?.extract()?,
        slug: request.get("slug")?.extract()?,
        message: request.get("message")?.extract()?,
        remediation: request.get("remediation")?.extract()?,
        subject: request.get("subject")?.extract()?,
        implementation_fingerprint: request.get("implementation_fingerprint")?.extract()?,
        config_json: plain_value(&request.get("config")?)?.to_string(),
        dialect: request.get("dialect")?.extract()?,
        project_dir: request.get("project_dir")?.extract()?,
    }))
}

fn python_value(py: Python<'_>, value: &Value) -> PyResult<Py<PyAny>> {
    match value {
        Value::Null => Ok(py.None()),
        Value::Bool(flag) => flag.into_py_any(py),
        Value::Number(number) => match (number.as_i64(), number.as_u64()) {
            (Some(integer), _) => integer.into_py_any(py),
            (None, Some(integer)) => integer.into_py_any(py),
            (None, None) => number.as_f64().unwrap_or(f64::NAN).into_py_any(py),
        },
        Value::String(text) => text.into_py_any(py),
        Value::Array(items) => {
            let values: Vec<Py<PyAny>> = items
                .iter()
                .map(|item| python_value(py, item))
                .collect::<PyResult<_>>()?;
            PyList::new(py, values)?.into_py_any(py)
        }
        Value::Object(entries) => {
            let dictionary: Bound<'_, PyDict> = PyDict::new(py);
            for (key, item) in entries {
                dictionary.set_item(key, python_value(py, item)?)?;
            }
            dictionary.into_py_any(py)
        }
    }
}

fn readset_tuple<'py>(py: Python<'py>, readset: &ReadSet) -> PyResult<Bound<'py, PyTuple>> {
    let keys: Vec<Bound<'py, PyTuple>> = readset
        .iter()
        .map(|key| PyTuple::new(py, key))
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, keys)
}

fn rules_error(py: Python<'_>, message: String) -> PyResult<pyo3::PyErr> {
    let class: Bound<'_, PyAny> = py.import(RULES_ERRORS_MODULE)?.getattr(RULES_ERROR)?;
    Ok(pyo3::PyErr::from_value(class.call1((message,))?))
}

fn stored_rules(path: &std::path::Path) -> StoredRules {
    let Ok(text) = std::fs::read_to_string(path) else {
        return StoredRules::new();
    };
    parse_custom_rule_cache(&text)
}

/// One custom-rule run's subjects, reused and new results, and the cache file it reads and writes.
#[pyclass(module = "sqlbuild._native")]
struct CustomRuleCache {
    path: Option<PathBuf>,
    rules: Vec<CustomRule>,
    project: SubjectsInput,
    stored: StoredRules,
    pending: Vec<ReadSet>,
    results: SubjectResults,
    hits: usize,
    misses: usize,
}

#[pymethods]
impl CustomRuleCache {
    /// Load the cache at `path` (`None` when caching is off) for `(code, identity, subject)` rules.
    #[new]
    #[pyo3(signature = (*, path, rules, target_name, models))]
    fn new(
        path: Option<PathBuf>,
        rules: Vec<(String, Option<String>, Option<String>)>,
        target_name: Option<String>,
        models: Vec<(String, String, Option<String>)>,
    ) -> Self {
        let project = SubjectsInput {
            target_name,
            models: models
                .into_iter()
                .map(|(path, name, materialized)| ModelSubjectInput {
                    path,
                    name,
                    materialized,
                })
                .collect(),
        };
        let mut rules: Vec<CustomRule> = rules
            .into_iter()
            .map(|(code, identity, subject)| CustomRule {
                subjects: rule_subjects(subject.as_deref(), &project),
                code,
                identity,
                subject,
            })
            .collect();
        rules.sort_by(|left, right| left.code.cmp(&right.code));
        let stored: StoredRules = path.as_deref().map(stored_rules).unwrap_or_default();
        let pending: Vec<ReadSet> = pending_readsets(&stored, &rules);
        Self {
            path,
            rules,
            project,
            stored,
            pending,
            results: SubjectResults::new(),
            hits: 0,
            misses: 0,
        }
    }

    /// Stored read sets whose current digest decides whether their results are reused.
    fn pending_readsets<'py>(&self, py: Python<'py>) -> PyResult<Vec<Bound<'py, PyTuple>>> {
        self.pending
            .iter()
            .map(|readset| readset_tuple(py, readset))
            .collect()
    }

    /// Reuse results given each pending read set's digest; returns the subjects still to run.
    #[pyo3(signature = (*, digests))]
    fn plan(&mut self, digests: Vec<Option<String>>) -> BTreeMap<String, Option<Vec<String>>> {
        if self.path.is_none() {
            self.misses = self.rules.len();
            return self
                .rules
                .iter()
                .map(|rule| (rule.code.clone(), None))
                .collect();
        }
        let current: BTreeMap<ReadSet, String> = self
            .pending
            .iter()
            .zip(digests)
            .filter_map(|(readset, digest)| Some((readset.clone(), digest?)))
            .collect();
        let lookup: CustomCacheLookup =
            lookup_custom_rule_cache(&self.stored, &self.rules, &current);
        self.results.extend(lookup.hits);
        self.hits = lookup.hit_count;
        self.misses = lookup.miss_count;
        lookup.plan
    }

    /// Record evaluated results; with caching on, validate them, store them and write the file.
    #[pyo3(signature = (*, evaluated))]
    fn record(&mut self, py: Python<'_>, evaluated: Vec<EvaluationPy<'_>>) -> PyResult<()> {
        let evaluations: Vec<CustomEvaluation> = evaluated
            .into_iter()
            .map(|(code, subject, cacheable, findings)| {
                Ok(CustomEvaluation {
                    code,
                    subject,
                    cacheable,
                    findings: findings.iter().map(plain_value).collect::<PyResult<_>>()?,
                })
            })
            .collect::<PyResult<_>>()?;
        let Some(path) = self.path.clone() else {
            self.extend_results(evaluations);
            return Ok(());
        };
        validate_custom_findings(&self.rules, &self.project, &evaluations)
            .map_err(|error| rules_error(py, error.0).unwrap_or_else(|error| error))?;
        self.stored = store_custom_results(&self.stored, &self.rules, &evaluations);
        self.extend_results(evaluations);
        let text: String = custom_rule_cache_text(&self.stored, &self.rules);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let temporary: PathBuf = path.with_extension(format!(
            "tmp-{}-{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        std::fs::write(&temporary, text)?;
        std::fs::rename(&temporary, &path)?;
        Ok(())
    }

    /// Every finding payload in rule code, then subject order.
    fn findings(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        ordered_custom_findings(&self.rules, &self.results)
            .iter()
            .map(|finding| python_value(py, finding))
            .collect()
    }

    #[getter]
    fn hits(&self) -> usize {
        self.hits
    }

    #[getter]
    fn misses(&self) -> usize {
        self.misses
    }
}

impl CustomRuleCache {
    fn extend_results(&mut self, evaluations: Vec<CustomEvaluation>) {
        for evaluation in evaluations {
            self.results
                .insert((evaluation.code, evaluation.subject), evaluation.findings);
        }
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<CustomRuleCache>()?;
    module.add_function(wrap_pyfunction!(custom_rule_identity, module)?)?;
    Ok(())
}
