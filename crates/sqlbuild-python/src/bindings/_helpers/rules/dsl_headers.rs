//! DSL header scanning, header lint rules and header formatting fixes over Python lint models.

use std::cell::RefCell;

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyListMethods, PyString, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_rules::dsl_headers::constants::RULE_HEADER_PARSE;
use sqlbuild_rules::dsl_headers::main::format_headers::format_headers;
use sqlbuild_rules::dsl_headers::main::inner_header_text::inner_header_text;
use sqlbuild_rules::dsl_headers::main::lint_headers::lint_headers;
use sqlbuild_rules::dsl_headers::main::measurement_body_ranges::measurement_body_ranges as measurement_ranges;
use sqlbuild_rules::dsl_headers::main::scan_headers::scan_headers as scan;
use sqlbuild_rules::dsl_headers::main::sql_body_ranges::sql_body_ranges as body_ranges;
use sqlbuild_rules::dsl_headers::models::{
    HeaderRulesConfig, HeaderSeverity, HeaderSpan, HeaderViolation, ParseFailure, ParseOutcome,
};
use sqlbuild_rules::dsl_headers::types::HeaderParser;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const NATIVE_MODULE: &str = "sqlbuild._native";
const LINT_MODELS_MODULE: &str = "sqlbuild.lint.models";
const LINT_TYPES_MODULE: &str = "sqlbuild.lint.types";
const DISCOVERY_ERRORS_MODULE: &str = "sqlbuild.compiler.discovery.exceptions";
const PATHLIB_MODULE: &str = "pathlib";
const SENTINEL_PATH: &str = "<lint>";
const ENGINE: &str = "sqlbuild";
const LINE_FEED: &str = "\n";
const CARRIAGE_RETURN_LINE_FEED: &str = "\r\n";
const FUNCTION_KIND: &str = "FUNCTION";

/// Header values parsed by `parse_header_values`, with Python's error classes.
struct PyHeaderParser<'py> {
    parse: Bound<'py, PyAny>,
    path: Bound<'py, PyAny>,
    syntax_error: Bound<'py, PyAny>,
    discovery_error: Bound<'py, PyAny>,
    /// The header syntax error of the last rejected parse.
    rejected: RefCell<Option<PyErr>>,
}

impl<'py> PyHeaderParser<'py> {
    fn new(py: Python<'py>) -> PyResult<Self> {
        Ok(Self {
            parse: imported(py, NATIVE_MODULE, "parse_header_values")?,
            path: imported(py, PATHLIB_MODULE, "Path")?.call1((SENTINEL_PATH,))?,
            syntax_error: imported(py, DISCOVERY_ERRORS_MODULE, "ModelSqlParseError")?,
            discovery_error: imported(py, DISCOVERY_ERRORS_MODULE, "DiscoveryError")?,
            rejected: RefCell::new(None),
        })
    }

    fn failure(&self, error: &PyErr) -> PyResult<ParseFailure> {
        let py: Python<'py> = self.parse.py();
        let value: Bound<'py, PyAny> = error.value(py).clone().into_any();
        let help: Option<String> = if value.is_instance(&self.discovery_error)? {
            value.getattr("help")?.extract()?
        } else {
            None
        };
        Ok(ParseFailure {
            message: value.str()?.extract()?,
            help,
        })
    }
}

impl<'py> HeaderParser for PyHeaderParser<'py> {
    type Values = Bound<'py, PyAny>;
    type Error = PyErr;

    fn parse(&self, kind: &str, inner: &str) -> ParseOutcome<Self::Values, Self::Error> {
        let py: Python<'py> = self.parse.py();
        let parsed: PyResult<Bound<'py, PyAny>> = call_with(
            &self.parse,
            &[
                ("header", PyString::new(py, inner).into_any()),
                ("file_path", self.path.clone()),
                ("statement_name", PyString::new(py, kind).into_any()),
                ("header_line", py.None().into_bound(py)),
            ],
        );
        let error: PyErr = match parsed {
            Ok(values) => return ParseOutcome::Parsed(values),
            Err(error) => error,
        };
        let failure: ParseFailure = match self.failure(&error) {
            Ok(failure) => failure,
            Err(failed) => {
                return ParseOutcome::Raised(
                    failed,
                    ParseFailure {
                        message: String::new(),
                        help: None,
                    },
                );
            }
        };
        if error.is_instance(py, &self.syntax_error) {
            self.rejected.replace(Some(error));
            ParseOutcome::Rejected(failure)
        } else {
            ParseOutcome::Raised(error, failure)
        }
    }

    fn description(&self, values: &Self::Values) -> PyResult<Option<String>> {
        let description: Bound<'py, PyAny> = values.call_method1("get", ("description",))?;
        if description.is_instance_of::<PyString>() {
            return description.extract().map(Some);
        }
        Ok(None)
    }

    fn same(&self, left: &Self::Values, right: &Self::Values) -> PyResult<bool> {
        left.eq(right)
    }
}

/// The models and enums header results are built as.
struct LintClasses<'py> {
    violation: Bound<'py, PyAny>,
    severity: Bound<'py, PyAny>,
}

impl<'py> LintClasses<'py> {
    fn new(py: Python<'py>) -> PyResult<Self> {
        Ok(Self {
            violation: imported(py, LINT_MODELS_MODULE, "LintViolation")?,
            severity: imported(py, LINT_TYPES_MODULE, "LintSeverity")?,
        })
    }

    fn violation(
        &self,
        file_path: &Bound<'py, PyAny>,
        violation: HeaderViolation,
    ) -> PyResult<Bound<'py, PyAny>> {
        let py: Python<'py> = file_path.py();
        let severity: &str = match violation.severity {
            HeaderSeverity::Fault => "FAULT",
            HeaderSeverity::Warning => "WARNING",
        };
        call_with(
            &self.violation,
            &[
                ("file_path", file_path.clone()),
                ("line", violation.line.into_pyobject(py)?.into_any()),
                ("column", violation.column.into_pyobject(py)?.into_any()),
                ("code", PyString::new(py, violation.code).into_any()),
                ("message", PyString::new(py, &violation.message).into_any()),
                ("severity", self.severity.getattr(severity)?),
                ("engine", PyString::new(py, ENGINE).into_any()),
                (
                    "remediation",
                    PyString::new(py, &violation.remediation).into_any(),
                ),
            ],
        )
    }

    fn violations(
        &self,
        file_path: &Bound<'py, PyAny>,
        violations: Vec<HeaderViolation>,
    ) -> PyResult<Vec<Bound<'py, PyAny>>> {
        violations
            .into_iter()
            .map(|violation| self.violation(file_path, violation))
            .collect()
    }
}

fn text(contents: &Bound<'_, PyAny>) -> PyResult<Vec<char>> {
    Ok(contents.extract::<String>()?.chars().collect())
}

fn rules_config(config: &Bound<'_, PyAny>) -> PyResult<HeaderRulesConfig> {
    Ok(HeaderRulesConfig {
        line_width: config.getattr("line_width")?.extract()?,
        max_description_lines: config.getattr("max_description_lines")?.extract()?,
    })
}

fn spans(headers: &Bound<'_, PyAny>) -> PyResult<Vec<HeaderSpan>> {
    headers
        .try_iter()?
        .map(|header| {
            let header: Bound<'_, PyAny> = header?;
            Ok(HeaderSpan {
                kind: header.getattr("kind")?.extract()?,
                start: header.getattr("start")?.extract()?,
                end: header.getattr("end")?.extract()?,
            })
        })
        .collect()
}

fn ranges<'py>(py: Python<'py>, ranges: Vec<(usize, usize)>) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(py, ranges)
}

/// Every DSL header span in `contents`, or only the first.
#[pyfunction]
#[pyo3(signature = (*, contents, first_only = false))]
fn scan_headers<'py>(
    contents: &Bound<'py, PyAny>,
    first_only: bool,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = contents.py();
    let class: Bound<'py, PyAny> = imported(py, LINT_MODELS_MODULE, "HeaderSpan")?;
    let headers: Vec<Bound<'py, PyAny>> = scan(&text(contents)?, first_only)
        .into_iter()
        .map(|header| {
            call_with(
                &class,
                &[
                    ("kind", PyString::new(py, &header.kind).into_any()),
                    ("start", header.start.into_pyobject(py)?.into_any()),
                    ("end", header.end.into_pyobject(py)?.into_any()),
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, headers)
}

/// Non-empty SQL body ranges around and between the headers.
#[pyfunction]
#[pyo3(signature = (*, contents, headers))]
fn sql_body_ranges<'py>(
    contents: &Bound<'py, PyAny>,
    headers: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    ranges(
        contents.py(),
        body_ranges(&text(contents)?, &spans(headers)?),
    )
}

/// The authored query ranges inside MEASURE and EVIDENCE blocks.
#[pyfunction]
#[pyo3(signature = (*, contents))]
fn measurement_body_ranges<'py>(contents: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
    ranges(contents.py(), measurement_ranges(&text(contents)?))
}

fn header_violations<'py>(
    contents: &[char],
    headers: &[HeaderSpan],
    config: &Bound<'py, PyAny>,
) -> PyResult<Vec<HeaderViolation>> {
    let parser: PyHeaderParser<'py> = PyHeaderParser::new(config.py())?;
    lint_headers(contents, headers, rules_config(config)?, &parser)
}

/// Every header rule violation of `headers` in `contents`.
#[pyfunction]
#[pyo3(signature = (*, contents, file_path, headers, config))]
fn lint_native_headers<'py>(
    contents: &Bound<'py, PyAny>,
    file_path: &Bound<'py, PyAny>,
    headers: &Bound<'py, PyAny>,
    config: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let violations: Vec<HeaderViolation> =
        header_violations(&text(contents)?, &spans(headers)?, config)?;
    let classes: LintClasses<'py> = LintClasses::new(contents.py())?;
    PyTuple::new(contents.py(), classes.violations(file_path, violations)?)
}

/// `contents` with header formatting fixes applied, and the faults relocation reported.
#[pyfunction]
#[pyo3(signature = (*, contents, file_path, config))]
fn format_native_headers<'py>(
    contents: &Bound<'py, PyAny>,
    file_path: &Bound<'py, PyAny>,
    config: &Bound<'py, PyAny>,
) -> PyResult<(String, Bound<'py, PyTuple>)> {
    let py: Python<'py> = contents.py();
    let parser: PyHeaderParser<'py> = PyHeaderParser::new(py)?;
    let (formatted, faults) = format_headers(&text(contents)?, rules_config(config)?, &parser)?;
    let classes: LintClasses<'py> = LintClasses::new(py)?;
    Ok((
        formatted.into_iter().collect(),
        PyTuple::new(py, classes.violations(file_path, faults)?)?,
    ))
}

/// The header-parse faults of one file.
fn parse_faults<'py>(
    classes: &LintClasses<'py>,
    (file_path, contents): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    config: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let contents: Vec<char> = text(contents)?;
    let violations: Vec<HeaderViolation> =
        header_violations(&contents, &scan(&contents, false), config)?
            .into_iter()
            .filter(|violation| violation.code == RULE_HEADER_PARSE)
            .collect();
    classes.violations(file_path, violations)
}

/// Batch parse formatter-owned headers before per-file formatting and linting.
#[pyfunction]
#[pyo3(signature = (*, files))]
fn prepare_native_header_cache(files: &Bound<'_, PyDict>) -> PyResult<()> {
    let mut headers: Vec<String> = Vec::new();
    for contents in files.values() {
        let contents: Vec<char> = text(&contents)?;
        for header in scan(&contents, false) {
            headers.push(
                inner_header_text(&contents[header.start..header.end])
                    .iter()
                    .collect(),
            );
        }
    }
    imported(files.py(), NATIVE_MODULE, "prepare_model_header_tokens")?.call1((headers,))?;
    Ok(())
}

/// Parse-safe files, and every file's authored newline convention.
#[pyfunction]
#[pyo3(signature = (*, files, config))]
fn safe_format_files<'py>(
    files: &Bound<'py, PyDict>,
    config: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PyDict>)> {
    let py: Python<'py> = files.py();
    let classes: LintClasses<'py> = LintClasses::new(py)?;
    let safe: Bound<'py, PyDict> = PyDict::new(py);
    let newlines: Bound<'py, PyDict> = PyDict::new(py);
    for (file_path, contents) in files.iter() {
        if parse_faults(&classes, (&file_path, &contents), config)?.is_empty() {
            safe.set_item(&file_path, &contents)?;
        }
    }
    for (file_path, contents) in files.iter() {
        let crlf: bool = contents
            .extract::<String>()?
            .contains(CARRIAGE_RETURN_LINE_FEED);
        newlines.set_item(
            file_path,
            if crlf {
                CARRIAGE_RETURN_LINE_FEED
            } else {
                LINE_FEED
            },
        )?;
    }
    Ok((safe, newlines))
}

/// Every rewrite whose header still parses, with the faults of the discarded ones appended.
#[pyfunction]
#[pyo3(signature = (*, updated, config, faults))]
fn reject_unparseable_header_rewrites<'py>(
    updated: &Bound<'py, PyDict>,
    config: &Bound<'py, PyAny>,
    faults: &Bound<'py, PyList>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PyList>)> {
    let classes: LintClasses<'py> = LintClasses::new(updated.py())?;
    let accepted: Bound<'py, PyDict> = updated.copy()?;
    for (file_path, contents) in updated.iter() {
        let parse: Vec<Bound<'py, PyAny>> =
            parse_faults(&classes, (&file_path, &contents), config)?;
        if parse.is_empty() {
            continue;
        }
        if accepted.contains(&file_path)? {
            accepted.del_item(&file_path)?;
        }
        for fault in parse {
            faults.append(fault)?;
        }
    }
    Ok((accepted, faults.clone()))
}

/// The SQL function argument names a FUNCTION header declares, lowercased and sorted.
#[pyfunction]
#[pyo3(signature = (*, contents, headers))]
fn external_identifiers_for_headers<'py>(
    contents: &Bound<'py, PyAny>,
    headers: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = contents.py();
    let text: Vec<char> = text(contents)?;
    let parser: PyHeaderParser<'py> = PyHeaderParser::new(py)?;
    for header in spans(headers)? {
        if header.kind != FUNCTION_KIND {
            continue;
        }
        let inner: String = inner_header_text(&text[header.start..header.end])
            .iter()
            .collect();
        let values: Bound<'py, PyAny> = match parser.parse(&header.kind, &inner) {
            ParseOutcome::Parsed(values) => values,
            ParseOutcome::Rejected(_) => {
                return Err(parser.rejected.take().unwrap_or_else(|| PyErr::fetch(py)));
            }
            ParseOutcome::Raised(error, _) => return Err(error),
        };
        let arguments: Bound<'py, PyAny> = values.call_method1("get", ("arguments",))?;
        let Ok(arguments) = arguments.downcast::<PyDict>() else {
            continue;
        };
        let mut names: Vec<String> = arguments
            .keys()
            .iter()
            .map(|name| name.str()?.call_method0("lower")?.extract())
            .collect::<PyResult<_>>()?;
        names.sort_unstable();
        return PyTuple::new(py, names);
    }
    Ok(PyTuple::empty(py))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scan_headers, module)?)?;
    module.add_function(wrap_pyfunction!(sql_body_ranges, module)?)?;
    module.add_function(wrap_pyfunction!(measurement_body_ranges, module)?)?;
    module.add_function(wrap_pyfunction!(lint_native_headers, module)?)?;
    module.add_function(wrap_pyfunction!(format_native_headers, module)?)?;
    module.add_function(wrap_pyfunction!(prepare_native_header_cache, module)?)?;
    module.add_function(wrap_pyfunction!(safe_format_files, module)?)?;
    module.add_function(wrap_pyfunction!(
        reject_unparseable_header_rewrites,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(external_identifiers_for_headers, module)?)?;
    Ok(())
}
