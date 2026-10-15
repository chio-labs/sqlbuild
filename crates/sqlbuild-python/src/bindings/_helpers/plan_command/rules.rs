//! `sqb rules`: list, show, install skills for, or run a selection of compiler rules.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python, pyfunction,
};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyListMethods, PyTuple};
use pyo3::wrap_pyfunction;

use crate::bindings::_helpers::command_runtime::adapters::resolve_cli_adapter;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const NATIVE_MODULE: &str = "sqlbuild._native";
const RULE_MODELS: &str = "sqlbuild._native";
const REJECT_UNIT_TESTS_MODULE: &str = "sqlbuild._native";
const GRAPH_SELECTION_MODULE: &str = "sqlbuild._native";
const LIST_ACTION: &str = "list";
const SHOW_ACTION: &str = "show";
const SKILLS_ACTION: &str = "skills";
const GENERIC_DIALECT: &str = "generic";
const USAGE_EXIT_CODE: i32 = 2;
const RESULT_FIELDS: [&str; 5] = [
    "findings",
    "evaluated_models",
    "unevaluated_resources",
    "cache_hits",
    "cache_misses",
];

/// `print(text)`, or `print(text, file=sys.stderr)`.
fn print_line(py: Python<'_>, text: &str, stderr: bool) -> PyResult<()> {
    let options: Bound<'_, PyDict> = PyDict::new(py);
    if stderr {
        options.set_item("file", py.import("sys")?.getattr("stderr")?)?;
    }
    imported(py, "builtins", "print")?.call((text,), Some(&options))?;
    Ok(())
}

fn rule_codes(catalogue: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    let mut codes: Vec<String> = Vec::new();
    for rule in catalogue.try_iter()? {
        codes.push(rule?.getattr("code")?.extract()?);
    }
    Ok(codes)
}

fn run_skills(
    request: &Bound<'_, PyAny>,
    config: &Bound<'_, PyAny>,
    project_dir: &Bound<'_, PyAny>,
) -> PyResult<i32> {
    let py: Python<'_> = request.py();
    let check: bool = request.getattr("skills_check")?.is_truthy()?;
    let fresh: bool = call_with(
        &imported(py, NATIVE_MODULE, "install_rules_skills")?,
        &[
            ("config", config.clone()),
            ("project_dir", project_dir.clone()),
            ("check", request.getattr("skills_check")?),
        ],
    )?
    .is_truthy()?;
    if !check {
        print_line(py, "Installed Rules skills", false)?;
        return Ok(0);
    }
    print_line(
        py,
        if fresh {
            "Rules skills are fresh"
        } else {
            "Rules skills are stale"
        },
        false,
    )?;
    Ok(if fresh { 0 } else { 1 })
}

fn list_rules(catalogue: &Bound<'_, PyAny>, json_output: bool) -> PyResult<i32> {
    let py: Python<'_> = catalogue.py();
    if !json_output {
        let mut lines: Vec<String> = Vec::new();
        for rule in catalogue.try_iter()? {
            let rule: Bound<'_, PyAny> = rule?;
            lines.push(format!(
                "{}  {}",
                rule.getattr("code")?.str()?,
                rule.getattr("message")?.str()?
            ));
        }
        print_line(py, &lines.join("\n"), false)?;
        return Ok(0);
    }
    let rules: Bound<'_, PyList> = PyList::empty(py);
    for rule in catalogue.try_iter()? {
        let rule: Bound<'_, PyAny> = rule?;
        let item: Bound<'_, PyDict> = PyDict::new(py);
        for field in ["code", "family", "message", "custom"] {
            item.set_item(field, rule.getattr(field)?)?;
        }
        let subject: Bound<'_, PyAny> = rule.getattr("subject")?;
        item.set_item(
            "subject",
            if subject.is_none() {
                subject
            } else {
                subject.getattr("value")?
            },
        )?;
        rules.append(item)?;
    }
    let payload: Bound<'_, PyDict> = PyDict::new(py);
    payload.set_item("rules", rules)?;
    let options: Bound<'_, PyDict> = PyDict::new(py);
    options.set_item("sort_keys", true)?;
    let text: String = imported(py, "json", "dumps")?
        .call((payload,), Some(&options))?
        .extract()?;
    print_line(py, &text, false)?;
    Ok(0)
}

fn show_rule(
    selector: &str,
    catalogue: &Bound<'_, PyAny>,
    config: &Bound<'_, PyAny>,
) -> PyResult<i32> {
    let py: Python<'_> = catalogue.py();
    for rule in catalogue.try_iter()? {
        let rule: Bound<'_, PyAny> = rule?;
        if rule.getattr("code")?.extract::<String>()? == selector {
            let text: String = call_with(
                &imported(py, NATIVE_MODULE, "format_rule")?,
                &[("rule", rule), ("config", config.clone())],
            )?
            .extract()?;
            print_line(py, &text, false)?;
            return Ok(0);
        }
    }
    print_line(py, &format!("Unknown rule: {selector}"), false)?;
    Ok(USAGE_EXIT_CODE)
}

/// The discovered project, its adapter, graph and selected keys a rule selection runs over.
struct RuleInputs<'py> {
    discovered: Bound<'py, PyAny>,
    adapter: Bound<'py, PyAny>,
    graph: Bound<'py, PyAny>,
    selected: Bound<'py, PyAny>,
}

fn rule_inputs<'py>(
    request: &Bound<'py, PyAny>,
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<RuleInputs<'py>> {
    let py: Python<'py> = request.py();
    let discovered: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[("project_dir", project_dir.clone())],
    )?;
    let select: Bound<'py, PyAny> = request.getattr("select")?;
    let exclude: Bound<'py, PyAny> = request.getattr("exclude")?;
    call_with(
        &imported(py, REJECT_UNIT_TESTS_MODULE, "reject_unit_test_selectors")?,
        &[
            ("select", select.clone()),
            ("exclude", exclude.clone()),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let adapter_name: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let adapter: Bound<'py, PyAny> = resolve_cli_adapter(&adapter_name, project_dir)?;
    let graph: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "build_project_graph")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("adapter", adapter.clone()),
        ],
    )?;
    let selected: Bound<'py, PyAny> = call_with(
        &imported(py, GRAPH_SELECTION_MODULE, "select_project_graph")?,
        &[
            ("graph", graph.clone()),
            ("select", select),
            ("exclude", exclude),
        ],
    )?;
    Ok(RuleInputs {
        discovered,
        adapter,
        graph,
        selected,
    })
}

fn run_rule_selection(
    request: &Bound<'_, PyAny>,
    (selector, catalogue): (&str, &Bound<'_, PyAny>),
    config: &Bound<'_, PyAny>,
    project_dir: &Bound<'_, PyAny>,
) -> PyResult<i32> {
    let py: Python<'_> = request.py();
    if !rule_codes(catalogue)?
        .iter()
        .any(|code| code.starts_with(selector))
    {
        print_line(py, &format!("Unknown rule or family: {selector}"), false)?;
        return Ok(USAGE_EXIT_CODE);
    }
    print_line(
        py,
        &format!("Evaluating rule selection {selector}..."),
        true,
    )?;
    let RuleInputs {
        discovered,
        adapter,
        graph,
        selected,
    } = rule_inputs(request, project_dir)?;
    let narrowed: bool =
        request.getattr("select")?.is_truthy()? || request.getattr("exclude")?.is_truthy()?;
    let replaced: Bound<'_, PyDict> = PyDict::new(py);
    replaced.set_item("select", PyTuple::new(py, [selector])?)?;
    replaced.set_item("ignore", PyTuple::empty(py))?;
    let dialect: Bound<'_, PyAny> = adapter.call_method0("sql_analysis_dialect")?;
    let result: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "run_rules")?,
        &[
            ("graph", graph),
            ("discovered_inputs", discovered),
            (
                "config",
                imported(py, "dataclasses", "replace")?.call((config,), Some(&replaced))?,
            ),
            ("project_dir", project_dir.clone()),
            (
                "dialect",
                if dialect.is_truthy()? {
                    dialect
                } else {
                    pyo3::types::PyString::new(py, GENERIC_DIALECT).into_any()
                },
            ),
            (
                "selected_keys",
                if narrowed {
                    selected
                } else {
                    py.None().into_bound(py)
                },
            ),
        ],
    )?;
    let note: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "format_skipped_type_proof_rules")?,
        &[("codes", result.getattr("skipped_type_proof_rules")?)],
    )?;
    if !note.is_none() {
        print_line(py, &format!("note: {}", note.str()?), true)?;
    }
    let fields: Bound<'_, PyDict> = PyDict::new(py);
    for field in RESULT_FIELDS {
        fields.set_item(field, result.getattr(field)?)?;
    }
    let text: String = call_with(
        &imported(py, NATIVE_MODULE, "format_rules_result")?,
        &[
            (
                "result",
                imported(py, RULE_MODELS, "RulesResult")?.call((), Some(&fields))?,
            ),
            ("json_output", request.getattr("json_output")?),
        ],
    )?
    .extract()?;
    print_line(py, &text, false)?;
    let findings: usize = result.getattr("findings")?.len()?;
    if findings > 0 {
        print_line(
            py,
            &format!("Rule selection {selector} failed with {findings} finding(s)."),
            true,
        )?;
        return Ok(1);
    }
    print_line(py, &format!("Rule selection {selector} passed."), true)?;
    Ok(0)
}

/// List, inspect, execute, or generate guidance for compiler rules.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_rules_command(request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let py: Python<'_> = request.py();
    let requested_dir: Bound<'_, PyAny> = request.getattr("project_dir")?;
    let project_dir: Bound<'_, PyAny> = if requested_dir.is_none() {
        imported(py, "pathlib", "Path")?.call_method0("cwd")?
    } else {
        requested_dir
    }
    .call_method0("resolve")?;
    let config: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "load_rules_config")?,
        &[("project_dir", project_dir.clone())],
    )?;
    let action: String = request.getattr("action")?.extract()?;
    if action == SKILLS_ACTION {
        return run_skills(request, &config, &project_dir);
    }
    let catalogue: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "build_rule_catalogue")?,
        &[
            ("config", config.clone()),
            ("project_dir", project_dir.clone()),
        ],
    )?;
    if action == LIST_ACTION {
        return list_rules(&catalogue, request.getattr("json_output")?.is_truthy()?);
    }
    let selector: Option<String> = request.getattr("rule_selector")?.extract()?;
    let Some(selector) = selector else {
        print_line(py, "A rule code or family prefix is required", false)?;
        return Ok(USAGE_EXIT_CODE);
    };
    if action == SHOW_ACTION {
        return show_rule(&selector, &catalogue, &config);
    }
    run_rule_selection(request, (&selector, &catalogue), &config, &project_dir)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_rules_command, module)?)
}
