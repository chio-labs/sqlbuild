//! Immutable event exporter accounting, failure and binding values Python reads.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python, pyclass, pymethods};
use pyo3::types::{PyDict, PyFrozenSet, PyTuple};
use sqlbuild_core::event_export::constants::EVENT_EXPORT_KINDS;
use sqlbuild_core::event_export::models::{
    ExportSeverity, ExportSnapshot, ExporterCounts, ExporterFilter,
};

use crate::bindings::_helpers::event_exporting::values::{
    accounting_repr, bound_exporter_arguments, counts_repr, python_repr, severity_from,
    severity_object, text_repr,
};

/// Frozen attempt counters for one exporter or their aggregate.
#[pyclass(module = "sqlbuild._native", frozen, eq, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub(crate) struct EventExporterCounts {
    pub(crate) counts: ExporterCounts,
}

/// Frozen accounting snapshot for one named exporter.
#[pyclass(module = "sqlbuild._native", frozen, eq, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub(crate) struct EventExporterAccounting {
    exporter_name: String,
    counts: ExporterCounts,
}

/// Final or point-in-time best-effort delivery accounting.
#[pyclass(module = "sqlbuild._native", frozen, eq, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub(crate) struct EventExportSummary {
    pub(crate) snapshot: ExportSnapshot,
}

/// Sanitized exporter failure information safe for diagnostics.
#[pyclass(module = "sqlbuild._native", frozen, eq, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub(crate) struct EventExporterFailure {
    pub(crate) exporter_name: String,
    pub(crate) error_type: String,
    pub(crate) event_kind: String,
    pub(crate) event_severity: ExportSeverity,
}

/// One lifecycle-event sink bound to command-scoped provider instances.
#[pyclass(module = "sqlbuild._native", frozen)]
#[derive(Debug)]
pub(crate) struct BoundEventExporter {
    pub(crate) name: String,
    pub(crate) function: Py<PyAny>,
    pub(crate) provider_arguments: Py<PyAny>,
    pub(crate) filter: ExporterFilter,
}

#[pymethods]
impl EventExporterCounts {
    #[getter]
    pub(crate) fn accepted(&self) -> u64 {
        self.counts.accepted
    }

    #[getter]
    pub(crate) fn filtered(&self) -> u64 {
        self.counts.filtered
    }

    #[getter]
    pub(crate) fn delivered(&self) -> u64 {
        self.counts.delivered
    }

    #[getter]
    pub(crate) fn failed(&self) -> u64 {
        self.counts.failed
    }

    #[getter]
    pub(crate) fn dropped(&self) -> u64 {
        self.counts.dropped
    }

    fn __repr__(&self) -> String {
        counts_repr(&self.counts)
    }
}

#[pymethods]
impl EventExporterAccounting {
    #[getter]
    pub(crate) fn exporter_name(&self) -> &str {
        &self.exporter_name
    }

    #[getter]
    pub(crate) fn counts(&self) -> EventExporterCounts {
        EventExporterCounts {
            counts: self.counts,
        }
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        accounting_repr(py, (&self.exporter_name, &self.counts))
    }
}

#[pymethods]
impl EventExportSummary {
    #[getter]
    pub(crate) fn aggregate(&self) -> EventExporterCounts {
        EventExporterCounts {
            counts: self.snapshot.aggregate,
        }
    }

    #[getter]
    pub(crate) fn per_exporter<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let items: Vec<EventExporterAccounting> = self
            .snapshot
            .per_exporter
            .iter()
            .map(|(name, counts)| EventExporterAccounting {
                exporter_name: name.clone(),
                counts: *counts,
            })
            .collect();
        PyTuple::new(py, items)
    }

    #[getter]
    pub(crate) fn queue_depth(&self) -> usize {
        self.snapshot.queue_depth
    }

    #[getter]
    pub(crate) fn queue_capacity(&self) -> usize {
        self.snapshot.queue_capacity
    }

    #[getter]
    pub(crate) fn flush_complete(&self) -> bool {
        self.snapshot.flush_complete
    }

    #[getter]
    pub(crate) fn accepted(&self) -> u64 {
        self.snapshot.aggregate.accepted
    }

    #[getter]
    pub(crate) fn filtered(&self) -> u64 {
        self.snapshot.aggregate.filtered
    }

    #[getter]
    pub(crate) fn delivered(&self) -> u64 {
        self.snapshot.aggregate.delivered
    }

    #[getter]
    pub(crate) fn failed(&self) -> u64 {
        self.snapshot.aggregate.failed
    }

    #[getter]
    pub(crate) fn dropped(&self) -> u64 {
        self.snapshot.aggregate.dropped
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let per_exporter: Vec<String> = self
            .snapshot
            .per_exporter
            .iter()
            .map(|(name, counts)| accounting_repr(py, (name, counts)))
            .collect::<PyResult<Vec<String>>>()?;
        let per_exporter: String = match per_exporter.as_slice() {
            [single] => format!("({single},)"),
            items => format!("({})", items.join(", ")),
        };
        Ok(format!(
            "EventExportSummary(aggregate={}, per_exporter={per_exporter}, queue_depth={}, \
             queue_capacity={}, flush_complete={})",
            counts_repr(&self.snapshot.aggregate),
            self.snapshot.queue_depth,
            self.snapshot.queue_capacity,
            if self.snapshot.flush_complete {
                "True"
            } else {
                "False"
            }
        ))
    }
}

#[pymethods]
impl EventExporterFailure {
    #[getter]
    pub(crate) fn exporter_name(&self) -> &str {
        &self.exporter_name
    }

    #[getter]
    pub(crate) fn error_type(&self) -> &str {
        &self.error_type
    }

    #[getter]
    pub(crate) fn event_kind(&self) -> &str {
        &self.event_kind
    }

    #[getter]
    pub(crate) fn event_severity<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        severity_object(py, self.event_severity)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "EventExporterFailure(exporter_name={}, error_type={}, event_kind={}, event_severity={})",
            text_repr(py, &self.exporter_name)?,
            text_repr(py, &self.error_type)?,
            text_repr(py, &self.event_kind)?,
            python_repr(&severity_object(py, self.event_severity)?)?
        ))
    }
}

#[pymethods]
impl BoundEventExporter {
    #[new]
    #[pyo3(signature = (*arguments, **options))]
    fn new(arguments: &Bound<'_, PyTuple>, options: Option<&Bound<'_, PyDict>>) -> PyResult<Self> {
        let [
            name,
            function,
            provider_arguments,
            event_kinds,
            min_severity,
        ] = bound_exporter_arguments(arguments, options)?;
        let (Some(name), Some(function), Some(provider_arguments)) =
            (name, function, provider_arguments)
        else {
            return Err(pyo3::exceptions::PyTypeError::new_err(
                "BoundEventExporter() missing required arguments",
            ));
        };
        Self::create(
            name.extract()?,
            (function.unbind(), provider_arguments.unbind()),
            (event_kinds.as_ref(), min_severity.as_ref()),
        )
    }

    #[getter]
    pub(crate) fn name(&self) -> &str {
        &self.name
    }

    #[getter]
    pub(crate) fn function(&self, py: Python<'_>) -> Py<PyAny> {
        self.function.clone_ref(py)
    }

    #[getter]
    pub(crate) fn provider_arguments(&self, py: Python<'_>) -> Py<PyAny> {
        self.provider_arguments.clone_ref(py)
    }

    #[getter]
    pub(crate) fn event_kinds<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyFrozenSet>> {
        PyFrozenSet::new(py, self.filter.event_kinds.iter())
    }

    #[getter]
    pub(crate) fn min_severity<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        severity_object(py, self.filter.min_severity)
    }
}

impl BoundEventExporter {
    /// A sink bound to `provider_arguments`, filtered by `event_kinds` and `min_severity` when given.
    pub(crate) fn create(
        name: String,
        (function, provider_arguments): (Py<PyAny>, Py<PyAny>),
        (event_kinds, min_severity): (Option<&Bound<'_, PyAny>>, Option<&Bound<'_, PyAny>>),
    ) -> PyResult<Self> {
        let event_kinds = match event_kinds {
            Some(kinds) => kinds
                .try_iter()?
                .map(|kind| kind.and_then(|kind| kind.extract::<String>()))
                .collect::<PyResult<_>>()?,
            None => EVENT_EXPORT_KINDS
                .iter()
                .map(|kind| (*kind).to_owned())
                .collect(),
        };
        let min_severity: ExportSeverity = match min_severity {
            Some(severity) => severity_from(severity)?,
            None => ExportSeverity::Debug,
        };
        Ok(Self {
            name,
            function,
            provider_arguments,
            filter: ExporterFilter {
                event_kinds,
                min_severity,
            },
        })
    }
}

impl EventExportSummary {
    /// A Python summary of `snapshot`.
    pub(crate) fn object(py: Python<'_>, snapshot: ExportSnapshot) -> PyResult<Py<Self>> {
        Py::new(py, Self { snapshot })
    }
}
