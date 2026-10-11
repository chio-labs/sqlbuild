//! Audits attached by the native loop, held by the compiled project, and their views.

use pyo3::exceptions::{PyIndexError, PyRuntimeError};
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::PyTuple;
use pyo3::{FromPyObject, pyclass, pymethods};

use crate::bindings::_helpers::compiled_project::compiled_model_view::object_key;
use crate::bindings::_helpers::compiled_project::function_views::ObjectKeyRow;
use crate::bindings::_helpers::compiled_project::model_input_view::{
    InputViewClasses, reference_tuple, view_classes,
};
use crate::bindings::_helpers::compiled_project::model_loop_host::ReferenceRow;
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;

const AUDIT_RESOURCE: &str = "audit";
const AUDIT_CLASSES: &str = "audits";
const NOT_ASSEMBLED: &str = "the audit was not assembled";

/// The Python enums an audit view projects its severity and attached target kind with.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct AuditClasses<'py> {
    audit_severity: Bound<'py, PyAny>,
    attached_target_kind: Bound<'py, PyAny>,
}

/// `(references as (kind, name, package), attached (kind, name))`.
pub(crate) type AuditAssemblyRow = (
    Vec<(String, String, Option<String>)>,
    Option<(String, String)>,
);

/// The target an attached audit checks: its kind, name and column.
pub(crate) struct AttachedTarget {
    pub(crate) kind: String,
    pub(crate) name: String,
    pub(crate) column: Option<String>,
}

/// What the audit loop attached for one singular audit block or attached generic audit.
pub(crate) struct AttachedAudit {
    /// The discovered (or built-in) audit file and block the SQL comes from.
    pub(crate) audit_file: Py<PyAny>,
    pub(crate) audit_block: Py<PyAny>,
    /// The block's name, else the file's stem.
    pub(crate) definition_name: String,
    pub(crate) sql_body: String,
    pub(crate) measurement: bool,
    pub(crate) evidence_sql: Option<String>,
    /// The authored measurement policy specs, carrying user values.
    pub(crate) thresholds: Py<PyAny>,
    pub(crate) minimum_samples: Py<PyAny>,
    pub(crate) evidence_limit: Py<PyAny>,
    pub(crate) references: Vec<ReferenceRow>,
    pub(crate) target: Option<AttachedTarget>,
    pub(crate) severity: &'static str,
    pub(crate) run_scope: String,
    pub(crate) always_run: bool,
    /// Usage records, the identities the scope index is built from.
    pub(crate) usages: Py<PyTuple>,
    pub(crate) name: Option<String>,
    pub(crate) description: Option<String>,
}

impl AttachedAudit {
    /// `_resolve_audit_name`: the instance name, else the definition name.
    fn compiled_name(&self) -> &str {
        self.name.as_deref().unwrap_or(&self.definition_name)
    }
}

/// One attached audit held by the compiled project.
pub(crate) struct AuditRecord {
    pub(crate) attached: AttachedAudit,
    /// The scope dependency keys native project assembly resolved, once it ran.
    scope_deps: Option<Vec<ObjectKeyRow>>,
    references: PyOnceLock<Py<PyTuple>>,
    key: PyOnceLock<Py<PyAny>>,
}

impl AuditRecord {
    pub(crate) fn new(attached: AttachedAudit) -> Self {
        Self {
            attached,
            scope_deps: None,
            references: PyOnceLock::new(),
            key: PyOnceLock::new(),
        }
    }

    /// Keep the scope dependency keys native project assembly resolved for the audit.
    pub(crate) fn set_scope_deps(&mut self, deps: Vec<ObjectKeyRow>) {
        self.scope_deps = Some(deps);
    }
}

fn read_audit<'py, T>(
    owner: &Py<NativeCompiledProject>,
    index: usize,
    py: Python<'py>,
    read: impl FnOnce(&AuditRecord, Python<'py>) -> PyResult<T>,
) -> PyResult<T> {
    let owner = owner.bind(py).borrow();
    let audit: &AuditRecord = owner
        .audits()
        .get(index)
        .ok_or_else(|| PyIndexError::new_err(index))?;
    read(audit, py)
}

fn audit_classes<'py>(
    owner: &Py<NativeCompiledProject>,
    py: Python<'py>,
) -> PyResult<AuditClasses<'py>> {
    owner
        .bind(py)
        .borrow()
        .input_classes(py)?
        .get_item(AUDIT_CLASSES)?
        .extract()
}

/// The attributes an audit's input and compiled views share.
macro_rules! audit_getters {
    ($view:ty, { $($extra:tt)* }) => {
        #[pymethods]
        impl $view {
            $($extra)*

            #[getter]
            fn audit_file(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
                read_audit(&self.owner, self.index, py, |audit, py| {
                    Ok(audit.attached.audit_file.clone_ref(py))
                })
            }

            #[getter]
            fn audit_block(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
                read_audit(&self.owner, self.index, py, |audit, py| {
                    Ok(audit.attached.audit_block.clone_ref(py))
                })
            }

            #[getter]
            fn sql_body(&self, py: Python<'_>) -> PyResult<String> {
                read_audit(&self.owner, self.index, py, |audit, _| {
                    Ok(audit.attached.sql_body.clone())
                })
            }

            #[getter]
            fn evaluation_mode(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
                read_audit(&self.owner, self.index, py, |audit, py| {
                    Ok(audit
                        .attached
                        .audit_block
                        .bind(py)
                        .getattr("evaluation_mode")?
                        .unbind())
                })
            }

            #[getter]
            fn measurement_contract(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
                read_audit(&self.owner, self.index, py, |audit, py| {
                    Ok(audit
                        .attached
                        .audit_block
                        .bind(py)
                        .getattr("measurement_contract")?
                        .unbind())
                })
            }

            #[getter]
            fn thresholds(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
                read_audit(&self.owner, self.index, py, |audit, py| {
                    Ok(audit.attached.thresholds.clone_ref(py))
                })
            }

            #[getter]
            fn minimum_samples(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
                read_audit(&self.owner, self.index, py, |audit, py| {
                    Ok(audit.attached.minimum_samples.clone_ref(py))
                })
            }

            #[getter]
            fn measure_sql(&self, py: Python<'_>) -> PyResult<Option<String>> {
                read_audit(&self.owner, self.index, py, |audit, _| {
                    Ok(audit
                        .attached
                        .measurement
                        .then(|| audit.attached.sql_body.clone()))
                })
            }

            #[getter]
            fn evidence_sql(&self, py: Python<'_>) -> PyResult<Option<String>> {
                read_audit(&self.owner, self.index, py, |audit, _| {
                    Ok(audit.attached.evidence_sql.clone())
                })
            }

            #[getter]
            fn evidence_limit(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
                read_audit(&self.owner, self.index, py, |audit, py| {
                    Ok(audit.attached.evidence_limit.clone_ref(py))
                })
            }

            #[getter]
            fn references(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
                let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
                read_audit(&self.owner, self.index, py, |audit, _| {
                    reference_tuple(&classes, &audit.attached.references, &audit.references)
                })
            }

            #[getter]
            fn attached_target_kind<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
                let classes: AuditClasses<'py> = audit_classes(&self.owner, py)?;
                read_audit(&self.owner, self.index, py, |audit, py| {
                    match &audit.attached.target {
                        Some(target) => classes.attached_target_kind.call1((&target.kind,)),
                        None => Ok(py.None().into_bound(py)),
                    }
                })
            }

            #[getter]
            fn attached_target_name(&self, py: Python<'_>) -> PyResult<Option<String>> {
                read_audit(&self.owner, self.index, py, |audit, _| {
                    Ok(audit.attached.target.as_ref().map(|target| target.name.clone()))
                })
            }

            #[getter]
            fn attached_column_name(&self, py: Python<'_>) -> PyResult<Option<String>> {
                read_audit(&self.owner, self.index, py, |audit, _| {
                    Ok(audit
                        .attached
                        .target
                        .as_ref()
                        .and_then(|target| target.column.clone()))
                })
            }

            #[getter]
            fn severity<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
                let classes: AuditClasses<'py> = audit_classes(&self.owner, py)?;
                read_audit(&self.owner, self.index, py, |audit, _| {
                    classes.audit_severity.call1((audit.attached.severity,))
                })
            }

            #[getter]
            fn run_scope(&self, py: Python<'_>) -> PyResult<String> {
                read_audit(&self.owner, self.index, py, |audit, _| {
                    Ok(audit.attached.run_scope.clone())
                })
            }

            #[getter]
            fn always_run(&self, py: Python<'_>) -> PyResult<bool> {
                read_audit(&self.owner, self.index, py, |audit, _| {
                    Ok(audit.attached.always_run)
                })
            }

            #[getter]
            fn description(&self, py: Python<'_>) -> PyResult<Option<String>> {
                read_audit(&self.owner, self.index, py, |audit, _| {
                    Ok(audit.attached.description.clone())
                })
            }
        }
    };
}

/// One attached audit, read from the compiled project that owns it.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeAuditInput {
    owner: Py<NativeCompiledProject>,
    index: usize,
}

impl NativeAuditInput {
    pub(crate) fn new(owner: Py<NativeCompiledProject>, index: usize) -> Self {
        Self { owner, index }
    }
}

audit_getters!(NativeAuditInput, {
    #[getter]
    fn declaration_usages(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        read_audit(&self.owner, self.index, py, |audit, py| {
            Ok(audit.attached.usages.clone_ref(py))
        })
    }

    #[getter]
    fn name(&self, py: Python<'_>) -> PyResult<Option<String>> {
        read_audit(&self.owner, self.index, py, |audit, _| {
            Ok(audit.attached.name.clone())
        })
    }

    /// `(references as (kind, name, package), attached (kind, name))` for project assembly.
    #[getter]
    fn assembly_row(&self, py: Python<'_>) -> PyResult<AuditAssemblyRow> {
        read_audit(&self.owner, self.index, py, |audit, _| {
            let attached: &AttachedAudit = &audit.attached;
            Ok((
                attached
                    .references
                    .iter()
                    .map(|(kind, name, package, _)| (kind.clone(), name.clone(), package.clone()))
                    .collect(),
                attached
                    .target
                    .as_ref()
                    .map(|target| (target.kind.clone(), target.name.clone())),
            ))
        })
    }
});

/// One assembled audit, read from the compiled project that owns it.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeCompiledAudit {
    owner: Py<NativeCompiledProject>,
    index: usize,
}

impl NativeCompiledAudit {
    pub(crate) fn new(owner: Py<NativeCompiledProject>, index: usize) -> Self {
        Self { owner, index }
    }
}

audit_getters!(NativeCompiledAudit, {
    /// The audit's planner-facing `CompiledObjectKey`.
    #[getter]
    fn key(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        read_audit(&self.owner, self.index, py, |audit, py| {
            audit
                .key
                .get_or_try_init(py, || {
                    object_key(
                        &classes.compiled,
                        AUDIT_RESOURCE,
                        audit.attached.compiled_name(),
                    )
                })
                .map(|key| key.clone_ref(py))
        })
    }

    /// The planner-facing keys of the resources the audit is selected with.
    #[getter]
    fn scope_deps<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        read_audit(&self.owner, self.index, py, |audit, py| {
            let deps: &[ObjectKeyRow] = audit
                .scope_deps
                .as_deref()
                .ok_or_else(|| PyRuntimeError::new_err(NOT_ASSEMBLED))?;
            let mut keys: Vec<Py<PyAny>> = Vec::with_capacity(deps.len());
            for (kind, name) in deps {
                keys.push(object_key(&classes.compiled, kind, name)?);
            }
            PyTuple::new(py, keys)
        })
    }

    #[getter]
    fn name(&self, py: Python<'_>) -> PyResult<String> {
        read_audit(&self.owner, self.index, py, |audit, _| {
            Ok(audit.attached.compiled_name().to_owned())
        })
    }

    #[getter]
    fn definition_name(&self, py: Python<'_>) -> PyResult<String> {
        read_audit(&self.owner, self.index, py, |audit, _| {
            Ok(audit.attached.definition_name.clone())
        })
    }
});
