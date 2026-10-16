//! Coverage, replay-requirement and latest-requirement projections over append-only events.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyString, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_state::microbatches::main::latest_requirement::latest_requirement;
use sqlbuild_state::microbatches::main::project_coverage::project_coverage;
use sqlbuild_state::microbatches::main::project_replay::project_replay;
use sqlbuild_state::microbatches::models::{
    BoundInterval, CompletionFact, CoveragePiece, CoverageProjection, ReplayProjection,
    ReplayState, ReplayVersions, RequirementFact, TextInterval,
};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::microbatches::conversion::{
    BoundParser, MODELS_MODULE, TYPES_MODULE, enum_text, optional_text, timestamp,
};

const COMPLETION_RECORD_TYPES: [&str; 2] = ["partition_completion", "synthetic_completion"];
const ORDINARY_COMPLETION: &str = "partition_completion";
const REPLAY_REQUIREMENT: &str = "replay_requirement";
const UNKNOWN_FINGERPRINT: &str = "unknown";

fn python_intervals<'py>(
    py: Python<'py>,
    intervals: &[TextInterval],
) -> PyResult<Bound<'py, PyTuple>> {
    let class: Bound<'py, PyAny> = imported(py, MODELS_MODULE, "MicrobatchInterval")?;
    let built: Vec<Bound<'py, PyAny>> = intervals
        .iter()
        .map(|interval| {
            call_with(
                &class,
                &[
                    ("start", PyString::new(py, &interval.start).into_any()),
                    ("end", PyString::new(py, &interval.end).into_any()),
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, built)
}

fn python_coverage<'py>(
    py: Python<'py>,
    projection: &CoverageProjection,
    events: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let projected_class: Bound<'py, PyAny> =
        imported(py, MODELS_MODULE, "ProjectedMicrobatchInterval")?;
    let mut projected: Vec<Bound<'py, PyAny>> = Vec::with_capacity(projection.segments.len());
    for segment in &projection.segments {
        let event: &Bound<'py, PyAny> = &events[segment.completion];
        projected.push(call_with(
            &projected_class,
            &[
                (
                    "start",
                    PyString::new(py, &segment.interval.start).into_any(),
                ),
                ("end", PyString::new(py, &segment.interval.end).into_any()),
                ("fingerprint_status", event.getattr("fingerprint_status")?),
                ("model_version_hash", event.getattr("model_version_hash")?),
                ("record_type", event.getattr("record_type")?),
                ("completion_type", event.getattr("completion_type")?),
                ("event_id", event.getattr("event_id")?),
            ],
        )?);
    }
    call_with(
        &imported(py, MODELS_MODULE, "MicrobatchCoverageProjection")?,
        &[
            ("intervals", PyTuple::new(py, projected)?.into_any()),
            (
                "contiguous_frontier",
                projection
                    .contiguous_frontier
                    .as_deref()
                    .into_bound_py_any(py)?,
            ),
            (
                "known_missing",
                python_intervals(py, &projection.known_missing)?.into_any(),
            ),
            (
                "unaccounted",
                python_intervals(py, &projection.unaccounted)?.into_any(),
            ),
            (
                "unknown_fingerprints",
                python_intervals(py, &projection.unknown_fingerprints)?.into_any(),
            ),
        ],
    )
}

/// Fold completion facts and classify uncovered expected intervals.
#[pyfunction(name = "project_microbatch_coverage")]
#[pyo3(signature = (*, events, expected_intervals, cursor_type))]
fn coverage<'py>(
    events: &Bound<'py, PyAny>,
    expected_intervals: &Bound<'py, PyAny>,
    cursor_type: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = events.py();
    let mut parser: BoundParser<'py> = BoundParser::new(cursor_type)?;
    let mut completion_events: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut completions: Vec<CompletionFact> = Vec::new();
    for event in events.try_iter()? {
        let event: Bound<'py, PyAny> = event?;
        let record_type: String = enum_text(&event.getattr("record_type")?)?;
        let (start, end) = (
            event.getattr("partition_start")?,
            event.getattr("partition_end")?,
        );
        if !COMPLETION_RECORD_TYPES.contains(&record_type.as_str())
            || start.is_none()
            || end.is_none()
        {
            continue;
        }
        completions.push(CompletionFact {
            interval: BoundInterval {
                start: parser.bound(&start)?,
                end: parser.bound(&end)?,
            },
            ordinary: record_type == ORDINARY_COMPLETION,
            unknown_fingerprint: enum_text(&event.getattr("fingerprint_status")?)?
                == UNKNOWN_FINGERPRINT,
            created: timestamp(&event.getattr("created_at")?)?,
            event_id: event.getattr("event_id")?.extract()?,
        });
        completion_events.push(event);
    }
    let expected: Vec<BoundInterval> = expected_intervals
        .try_iter()?
        .map(|interval| parser.interval(&interval?))
        .collect::<PyResult<_>>()?;
    python_coverage(
        py,
        &project_coverage(&completions, &expected),
        &completion_events,
    )
}

fn replay_state_member(state: ReplayState) -> &'static str {
    match state {
        ReplayState::Incomplete => "INCOMPLETE",
        ReplayState::VerifiedComplete => "VERIFIED_COMPLETE",
        ReplayState::CompleteWithUnknownFingerprints => "COMPLETE_WITH_UNKNOWN_FINGERPRINTS",
        ReplayState::Superseded => "SUPERSEDED",
    }
}

/// Derive replay completion without writing mutable requirement status.
#[pyfunction(name = "project_replay_requirement")]
#[pyo3(signature = (**request))]
fn replay<'py>(request: Option<&Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyAny>> {
    let request = Request::new("project_replay_requirement", request)?;
    let py: Python<'py> = request.py();
    let requirement: Bound<'py, PyAny> = request.get("requirement")?;
    let current: String = request.get("current_model_version_hash")?.extract()?;
    let required: Option<String> =
        optional_text(&requirement.getattr("required_model_version_hash")?)?;
    let versions = ReplayVersions {
        required: required.as_deref(),
        current: &current,
    };
    let expected_objects: Vec<Bound<'py, PyAny>> = request
        .get("expected_intervals")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let mut expected: Vec<BoundInterval> = Vec::new();
    let mut pieces: Vec<CoveragePiece> = Vec::new();
    if required.as_deref() == Some(current.as_str()) {
        let mut parser: BoundParser<'py> = BoundParser::new(&request.get("cursor_type")?)?;
        for interval in &expected_objects {
            expected.push(parser.interval(interval)?);
        }
        for piece in request.get("coverage")?.getattr("intervals")?.try_iter()? {
            let piece: Bound<'py, PyAny> = piece?;
            pieces.push(CoveragePiece {
                interval: parser.interval(&piece)?,
                unknown_fingerprint: enum_text(&piece.getattr("fingerprint_status")?)?
                    == UNKNOWN_FINGERPRINT,
                model_version_hash: optional_text(&piece.getattr("model_version_hash")?)?,
            });
        }
    }
    let projection: ReplayProjection = project_replay(versions, &expected, &pieces);
    let selected = |indexes: &[usize]| {
        PyTuple::new(
            py,
            indexes.iter().map(|index| expected_objects[*index].clone()),
        )
    };
    call_with(
        &imported(py, MODELS_MODULE, "ReplayRequirementProjection")?,
        &[
            ("requirement", requirement),
            (
                "state",
                imported(py, TYPES_MODULE, "ReplayRequirementState")?
                    .getattr(replay_state_member(projection.state))?,
            ),
            ("missing", selected(&projection.missing)?.into_any()),
            (
                "unknown_fingerprints",
                selected(&projection.unknown_fingerprints)?.into_any(),
            ),
        ],
    )
}

/// Return only the latest requirement created for the currently compiled version.
#[pyfunction(name = "latest_active_replay_requirement")]
#[pyo3(signature = (*, events, current_model_version_hash))]
fn latest<'py>(
    events: &Bound<'py, PyAny>,
    current_model_version_hash: &str,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let objects: Vec<Bound<'py, PyAny>> = events.try_iter()?.collect::<PyResult<_>>()?;
    let mut facts: Vec<RequirementFact> = Vec::with_capacity(objects.len());
    for event in &objects {
        let is_requirement: bool = enum_text(&event.getattr("record_type")?)? == REPLAY_REQUIREMENT;
        let required: Option<String> =
            optional_text(&event.getattr("required_model_version_hash")?)?;
        let matching: bool =
            is_requirement && required.as_deref() == Some(current_model_version_hash);
        facts.push(RequirementFact {
            is_requirement,
            required_model_version_hash: required,
            created: if matching {
                timestamp(&event.getattr("created_at")?)?
            } else {
                0.0
            },
            event_id: event.getattr("event_id")?.extract()?,
        });
    }
    Ok(latest_requirement(&facts, current_model_version_hash).map(|index| objects[index].clone()))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(coverage, module)?)?;
    module.add_function(wrap_pyfunction!(replay, module)?)?;
    module.add_function(wrap_pyfunction!(latest, module)?)
}
