//! `sqb review`: plan the changed set, build it in a run-owned schema, test, compare and report.

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use std::time::Instant;

use pyo3::exceptions::PyException;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::review_command::constants::{
    BUILT_NODE, FAILED_NODE, FINDING_NODE, MODEL_KIND, NOT_VALIDATED_NODE, OK_NODE, PLANNED_STATUS,
};
use sqlbuild_analysis::review_command::main::plan_review::plan_review;
use sqlbuild_analysis::review_command::main::render_review_json::render_review_json;
use sqlbuild_analysis::review_command::main::render_review_markdown::render_review_markdown;
use sqlbuild_analysis::review_command::main::render_review_text::render_review_text;
use sqlbuild_analysis::review_command::main::review_outcome::review_outcome;
use sqlbuild_analysis::review_command::models::{
    DownstreamPolicy, NodeReport, ReviewFinding, ReviewNode, ReviewPlan, ReviewReport,
    ReviewSchemaReport,
};
use sqlbuild_core::git_revisions::main::head_commit::head_commit;

use crate::bindings::_helpers::boundary::python_calls::imported;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::review_command::comparison::{
    ComparisonContext, Comparisons, compare_models,
};
use crate::bindings::_helpers::review_command::execution::{
    BuildOutcome, RunInputs, build_validated, incremental_starts, run_changed_tests,
};
use crate::bindings::_helpers::review_command::impact::affected_columns;
use crate::bindings::_helpers::review_command::planning::{
    ReviewProject, ReviewSettings, discover, review_project, review_settings, selected_tokens,
};
use crate::bindings::_helpers::review_command::schema::{
    ReviewSchema, connection_config, create_review_schema, drop_review_schema, review_schema,
    with_review_target,
};
use crate::bindings::_helpers::review_command::support::{
    emit, error_parts, failed_error, invocation_id, optional_text, phase, plan_error, utc_now,
};

const SUCCESS_STATUS: &str = "success";
const SKIPPED_STATUS: &str = "skipped";
const REVIEW_WORK_DIRECTORY: [&str; 2] = ["target", "review"];

/// The nodes the changed set reaches, with edges between them.
fn impact_edges(project: &ReviewProject<'_>, plan: &ReviewPlan) -> Vec<(String, String)> {
    let affected: BTreeSet<&str> = plan
        .changed
        .iter()
        .map(|node| node.name.as_str())
        .chain(plan.not_validated.iter().map(|node| node.name.as_str()))
        .chain(plan.validated.iter().map(String::as_str))
        .collect();
    let mut edges: Vec<(String, String)> = Vec::new();
    for (upstream, children) in &project.review_graph.downstream {
        if !affected.contains(upstream.as_str()) {
            continue;
        }
        for child in children {
            if affected.contains(child.as_str()) {
                edges.push((upstream.clone(), child.clone()));
            }
        }
    }
    edges
}

/// Upstream nodes of the validated set that the build reads from `--against`.
fn deferred(project: &ReviewProject<'_>, validated: &[String]) -> Vec<String> {
    let built: BTreeSet<&str> = validated.iter().map(String::as_str).collect();
    let mut upstream: BTreeSet<String> = BTreeSet::new();
    for (parent, children) in &project.review_graph.downstream {
        if !built.contains(parent.as_str())
            && children.iter().any(|child| built.contains(child.as_str()))
        {
            upstream.insert(parent.clone());
        }
    }
    project
        .review_graph
        .order
        .iter()
        .filter(|name| upstream.contains(*name))
        .cloned()
        .collect()
}

/// The impact tree's nodes before anything runs.
fn planned_nodes(project: &ReviewProject<'_>, plan: &ReviewPlan, dry_run: bool) -> Vec<NodeReport> {
    let changed: BTreeSet<&str> = plan.changed.iter().map(|node| node.name.as_str()).collect();
    let validated: BTreeSet<&str> = plan.validated.iter().map(String::as_str).collect();
    let left_out: BTreeMap<&str, &str> = plan
        .not_validated
        .iter()
        .map(|node| (node.name.as_str(), node.reason.as_str()))
        .collect();
    project
        .review_graph
        .order
        .iter()
        .filter(|name| validated.contains(name.as_str()) || left_out.contains_key(name.as_str()))
        .map(|name| {
            let node: &ReviewNode = &project.review_graph.nodes[name];
            let reason: Option<&str> = left_out.get(name.as_str()).copied();
            NodeReport {
                name: name.clone(),
                kind: node.kind.clone(),
                critical: node.critical,
                changed: changed.contains(name.as_str()),
                status: match (reason, dry_run) {
                    (Some(_), _) => NOT_VALIDATED_NODE.to_owned(),
                    (None, true) => PLANNED_STATUS.to_owned(),
                    (None, false) => BUILT_NODE.to_owned(),
                },
                reason: reason.map(str::to_owned),
                ..NodeReport::default()
            }
        })
        .collect()
}

/// Settle each node's status from its build, audits, tests and comparison.
fn settle_nodes(
    report: &mut ReviewReport,
    build: &BuildOutcome,
    comparisons: Comparisons,
    affected: &BTreeMap<String, Vec<String>>,
) {
    let mut findings: Vec<ReviewFinding> = comparisons.findings;
    for (node, audit) in &build.failed_audits {
        findings.push(ReviewFinding {
            node: node.clone(),
            kind: "audit".to_owned(),
            metric: format!("audit {audit} failed"),
            limit: "passes".to_owned(),
            ..ReviewFinding::default()
        });
    }
    let with_findings: BTreeSet<String> = findings
        .iter()
        .map(|finding| finding.node.clone())
        .collect();
    let mut by_node: BTreeMap<String, sqlbuild_analysis::review_command::models::NodeComparison> =
        comparisons.by_node;
    for node in &mut report.nodes {
        node.affected_columns = affected.get(&node.name).cloned().unwrap_or_default();
        if node.status == NOT_VALIDATED_NODE {
            continue;
        }
        let status: Option<String> = build.statuses.get(&node.name).cloned();
        node.build_status.clone_from(&status);
        node.comparison = by_node.remove(&node.name);
        let blocked: bool = build.audit_blocked.contains(&node.name);
        node.status = match status.as_deref() {
            _ if with_findings.contains(&node.name) => FINDING_NODE.to_owned(),
            Some(SKIPPED_STATUS) => {
                node.reason = Some("skipped after an upstream failure".to_owned());
                NOT_VALIDATED_NODE.to_owned()
            }
            Some(SUCCESS_STATUS) | None if blocked => FINDING_NODE.to_owned(),
            Some(SUCCESS_STATUS) => match &node.comparison {
                Some(comparison) if comparison.complete && comparison.mode != "none" => {
                    OK_NODE.to_owned()
                }
                _ => BUILT_NODE.to_owned(),
            },
            _ if blocked => FINDING_NODE.to_owned(),
            _ => FAILED_NODE.to_owned(),
        };
    }
    for failure in &report.tests.failures {
        findings.push(ReviewFinding {
            node: failure.trim_start_matches("unit test ").to_owned(),
            kind: "test".to_owned(),
            metric: "unit test failed".to_owned(),
            limit: "passes".to_owned(),
            ..ReviewFinding::default()
        });
    }
    report.findings = findings;
    report.incomplete = comparisons.incomplete;
}

/// Everything that needs the review schema: clone, build, tests, comparison and impact.
fn validate(
    (request, stream, machine): (&Bound<'_, PyAny>, &Bound<'_, PyAny>, bool),
    (settings, project, schema): (&ReviewSettings, &ReviewProject<'_>, &ReviewSchema<'_>),
    (connection_config, connection): (&Bound<'_, PyAny>, &Bound<'_, PyAny>),
    report: &mut ReviewReport,
) -> PyResult<()> {
    let review_discovered: Bound<'_, PyAny> =
        with_review_target(&project.discovered, settings, schema)?;
    let work_dir: PathBuf = REVIEW_WORK_DIRECTORY
        .iter()
        .fold(project.project_dir.extract::<PathBuf>()?, |path, part| {
            path.join(part)
        })
        .join(&schema.name);
    std::fs::create_dir_all(&work_dir)
        .map_err(|error| pyo3::exceptions::PyOSError::new_err(error.to_string()))?;
    let inputs: RunInputs<'_, '_> = RunInputs {
        request,
        project_dir: &project.project_dir,
        review_discovered: &review_discovered,
        review_target: &schema.name,
        work_dir: &work_dir,
        machine,
    };
    let stateful: Vec<String> = report
        .plan
        .validated
        .iter()
        .filter(|name| project.stateful.contains(*name))
        .cloned()
        .collect();
    report.incremental_starts =
        incremental_starts(&inputs, (settings, &project.adapter), &stateful)?;
    let validated: Vec<String> = report.plan.validated.clone();
    let count: usize = validated.len();
    let build: BuildOutcome = phase(
        stream,
        (
            &format!(
                "Building {count} changed and downstream nodes into {} (unchanged upstream from {})",
                schema.name, settings.against
            ),
            "Built the review nodes",
            "Review build failed",
        ),
        || build_validated(&inputs, settings, (&project.review_graph, &validated)),
    )?;
    report.audits = build.audits.clone();
    report.tests = phase(
        stream,
        (
            &format!("Running unit tests affected since {}", project.reference),
            "Ran affected unit tests",
            "Unit tests failed to run",
        ),
        || run_changed_tests(&inputs, settings),
    )?;
    let comparable: Vec<&ReviewNode> = validated
        .iter()
        .filter(|name| build.statuses.get(*name).map(String::as_str) == Some(SUCCESS_STATUS))
        .filter_map(|name| project.review_graph.nodes.get(name))
        .filter(|node| node.kind == MODEL_KIND)
        .collect();
    let context: ComparisonContext<'_, '_> = ComparisonContext {
        request,
        discovered: &review_discovered,
        adapter: &project.adapter,
        connection,
        connection_config,
        review_target: &schema.name,
    };
    let comparisons: Comparisons = phase(
        stream,
        (
            &format!(
                "Comparing {} models with {}",
                comparable.len(),
                settings.against
            ),
            "Compared the review models",
            "Comparison failed",
        ),
        || compare_models(&context, settings, &comparable),
    )?;
    let affected_set: BTreeSet<String> =
        report.nodes.iter().map(|node| node.name.clone()).collect();
    let changed: Vec<String> = report
        .plan
        .changed
        .iter()
        .map(|node| node.name.clone())
        .collect();
    let affected: BTreeMap<String, Vec<String>> = affected_columns(
        &project.project,
        (&changed, &affected_set),
        &comparisons.by_node,
    )?;
    settle_nodes(report, &build, comparisons, &affected);
    Ok(())
}

/// Create the review schema, validate inside it, and always drop it.
fn run_in_schema(
    (request, stream, machine): (&Bound<'_, PyAny>, &Bound<'_, PyAny>, bool),
    (settings, project): (&ReviewSettings, &ReviewProject<'_>),
    report: &mut ReviewReport,
) -> PyResult<()> {
    let py: Python<'_> = request.py();
    let config: Bound<'_, PyAny> = connection_config(
        request,
        (&project.project_dir, &project.discovered),
        settings,
    )?;
    let adapter: &Bound<'_, PyAny> = &project.adapter;
    let connection: Bound<'_, PyAny> = adapter.call_method1("connect", (&config,))?;
    let run_id: String = report
        .invocation_id
        .clone()
        .unwrap_or_else(|| format!("{:x}", std::process::id()));
    let schema: ReviewSchema<'_> = review_schema(
        (&project.project, &project.discovered),
        settings,
        (utc_now(py)?, &report.baseline.head, &run_id),
    )?;
    report.schema = Some(ReviewSchemaReport {
        database: schema.database.clone(),
        name: schema.name.clone(),
        ..ReviewSchemaReport::default()
    });
    let created: PyResult<()> = phase(
        stream,
        (
            &format!("Creating review schema {}", schema.name),
            "Created the review schema",
            "Could not create the review schema",
        ),
        || create_review_schema((adapter, &connection), &schema),
    );
    let worked: PyResult<()> = match created {
        Ok(()) => {
            if let Some(state) = report.schema.as_mut() {
                state.created = true;
            }
            validate(
                (request, stream, machine),
                (settings, project, &schema),
                (&config, &connection),
                report,
            )
        }
        Err(error) => Err(error),
    };
    let created: bool = report.schema.as_ref().is_some_and(|state| state.created);
    if created {
        let dropped: PyResult<bool> = phase(
            stream,
            (
                &format!("Dropping review schema {}", schema.name),
                "Dropped the review schema",
                "Could not drop the review schema",
            ),
            || drop_review_schema((adapter, &connection), &schema),
        );
        if let Some(state) = report.schema.as_mut() {
            match dropped {
                Ok(true) => state.dropped = true,
                Ok(false) => {
                    state.error = Some("the schema still exists after the drop".to_owned())
                }
                Err(error) => state.error = Some(error_parts(py, &error).message),
            }
        }
    }
    let _ = adapter.call_method1("close", (&connection,));
    worked
}

fn review(
    (request, stream, machine): (&Bound<'_, PyAny>, &Bound<'_, PyAny>, bool),
    report: &mut ReviewReport,
) -> PyResult<()> {
    let py: Python<'_> = request.py();
    let (project_dir, discovered) = discover(request)?;
    let settings: ReviewSettings = review_settings(request, (&project_dir, &discovered))?;
    report.baseline.against.clone_from(&settings.against);
    report.baseline.target = Some(settings.target.clone());
    report.baseline.since_ref.clone_from(&settings.since);
    report.plan.policy = settings.policy;
    let directory: PathBuf = project_dir.extract()?;
    report.baseline.head = head_commit(&directory).unwrap_or_default();
    let project: ReviewProject<'_> = phase(
        stream,
        (
            "Planning the review",
            "Planned the review",
            "Planning failed",
        ),
        || review_project(request, (project_dir, discovered), &settings, stream),
    )?;
    report.baseline.since_ref.clone_from(&project.reference);
    report.baseline.merge_base.clone_from(&project.merge_base);
    report.changes_json = project.changes_json.clone();
    report.changed_declarations = project.changed_declarations.clone();
    let tokens = selected_tokens(request, &project.graph)?;
    report.plan = plan_review(
        &project.review_graph,
        &project.changed,
        settings.policy,
        tokens.as_deref(),
    )
    .map_err(|error| plan_error(py, &error))?;
    report.impact_edges = impact_edges(&project, &report.plan);
    report.nodes = planned_nodes(&project, &report.plan, report.dry_run);
    report.deferred = deferred(&project, &report.plan.validated);
    emit(
        stream,
        &format!(
            "Review plan: {} changed, {} to build, {} left out (--downstream {})",
            report.plan.changed.len(),
            report.plan.validated.len(),
            report.plan.not_validated.len(),
            match settings.policy {
                DownstreamPolicy::Critical => "critical",
                DownstreamPolicy::All => "all",
                DownstreamPolicy::None => "none",
            },
        ),
    )?;
    if report.dry_run || report.plan.validated.is_empty() {
        return Ok(());
    }
    run_in_schema((request, stream, machine), (&settings, &project), report)
}

fn publish(request: &Bound<'_, PyAny>, report: &ReviewReport, machine: bool) -> PyResult<()> {
    let py: Python<'_> = request.py();
    if let Some(path) = optional_text(&native_field(request, "markdown_path")?)? {
        let path: PathBuf = PathBuf::from(path);
        if let Some(parent) = path
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            std::fs::create_dir_all(parent)
                .map_err(|error| pyo3::exceptions::PyOSError::new_err(error.to_string()))?;
        }
        std::fs::write(&path, render_review_markdown(report))
            .map_err(|error| pyo3::exceptions::PyOSError::new_err(error.to_string()))?;
    }
    let stdout: Bound<'_, PyAny> = imported(py, "sys", "stdout")?;
    let document: String = if machine {
        render_review_json(report)
    } else {
        render_review_text(report)
    };
    stdout.call_method1("write", (document,))?;
    stdout.call_method0("flush")?;
    Ok(())
}

/// Run one `sqb review` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
pub(crate) fn run_review_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let started: Instant = Instant::now();
    let machine: bool = native_field(request, "json_output")?.is_truthy()?;
    let debug: bool = native_field(request, "debug")?.is_truthy()?;
    let stream: Bound<'_, PyAny> = imported(
        py,
        "sys",
        if machine || debug { "stderr" } else { "stdout" },
    )?;
    let mut report: ReviewReport = ReviewReport {
        version: env!("CARGO_PKG_VERSION").to_owned(),
        dry_run: native_field(request, "dry_run")?.is_truthy()?,
        invocation_id: invocation_id(py)?,
        ..ReviewReport::default()
    };
    let outcome: PyResult<()> = review((request, &stream, machine), &mut report);
    report.duration_seconds = started.elapsed().as_secs_f64();
    let cause: Option<PyErr> = outcome.err();
    if let Some(error) = &cause {
        report.error = Some(error_parts(py, error));
    }
    publish(request, &report, machine)?;
    if let Some(cause) = cause {
        if !cause.is_instance_of::<PyException>(py) {
            return Err(cause);
        }
        let error = report.error.clone().unwrap_or_default();
        return Err(failed_error(py, &error, Some(cause)));
    }
    Ok(review_outcome(&report).1)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_review_command, module)?)
}
