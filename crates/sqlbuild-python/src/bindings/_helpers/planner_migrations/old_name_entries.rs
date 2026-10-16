//! Assemble new and resumed old-name view steps from recorded facts.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::planner_migrations::column_objects::{model, native, text};
use crate::bindings::_helpers::planner_migrations::constants::{PENDING_ARCHIVE, PENDING_VIEW};
use crate::bindings::_helpers::planner_migrations::models::OldNamePlanner;
use crate::bindings::_helpers::planner_migrations::old_name_objects::{
    expires, location, relation, retention, stores_history,
};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyBool, PyList, PyTuple};

impl<'py> OldNamePlanner<'py> {
    pub(super) fn new(
        (runtime, columns): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
        models: Vec<Bound<'py, PyAny>>,
        histories: Vec<Bound<'py, PyAny>>,
        views: Bound<'py, PyAny>,
    ) -> PyResult<Self> {
        let runtime = runtime.clone();
        let py = runtime.py();
        let project_config = runtime.getattr("project_config")?;
        let config = if project_config.is_none() {
            registry::class(py, RecordId::MigrationsConfig)?.call0()?
        } else {
            project_config.getattr("migrations")?
        };
        Ok(Self {
            models,
            histories,
            views,
            columns: columns.clone(),
            retention: config.getattr("old_name_views")?,
            now: runtime.getattr("invocation_time")?,
            runtime,
        })
    }

    fn newest(
        &self,
        destination: &Bound<'py, PyAny>,
        origin: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        let mut newest: Option<(Bound<'py, PyTuple>, Bound<'py, PyAny>)> = None;
        for history in &self.histories {
            let movement = history.getattr("move")?;
            if !movement
                .getattr("destination")?
                .call_method1("matches", (destination,))?
                .is_truthy()?
            {
                continue;
            }
            if let Some(origin) = origin
                && !movement
                    .getattr("origin")?
                    .call_method1("matches", (origin,))?
                    .is_truthy()?
            {
                continue;
            }
            let key = PyTuple::new(
                self.runtime.py(),
                [
                    movement.getattr("created_at")?,
                    movement.getattr("event_id")?,
                ],
            )?;
            if let Some((previous, _)) = &newest
                && !key.gt(previous)?
            {
                continue;
            }
            newest = Some((key, history.clone()));
        }
        Ok(newest.map(|(_, history)| history))
    }

    pub(super) fn for_migration(
        &self,
        entry: &Bound<'py, PyAny>,
        item: &Bound<'py, PyAny>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        if entry.getattr("blocks_build")?.is_truthy()? {
            return Ok(None);
        }
        let decision = entry.getattr("decision")?;
        let completed = !entry.getattr("completed_at")?.is_none();
        if decision.getattr("moves_data")?.is_truthy()? || (decision.eq("renamed")? && !completed) {
            return self.new_move(entry, item).map(Some);
        }
        if decision.eq("done")? || (decision.eq("renamed")? && completed) {
            let origin = relation(&entry.getattr("origin")?)?;
            if let Some(history) =
                self.newest(&relation(&entry.getattr("destination")?)?, Some(&origin))?
            {
                return self.resume(&history, item);
            }
        }
        Ok(None)
    }

    pub(super) fn pending_for(
        &self,
        item: &Bound<'py, PyAny>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        let Some(history) = self.newest(&relation(&item.getattr("destination")?)?, None)? else {
            return Ok(None);
        };
        if !history
            .getattr("move")?
            .getattr("destination_model")?
            .eq(item.getattr("name")?)?
        {
            return Ok(None);
        }
        let Some(planned) = self.resume(&history, item)? else {
            return Ok(None);
        };
        if planned.getattr("runs_steps")?.is_truthy()?
            || (planned.getattr("action")?.eq("none")?
                && !planned.getattr("migration_event_id")?.is_none())
        {
            Ok(Some(planned))
        } else {
            Ok(None)
        }
    }

    fn skip(
        &self,
        origin: &Bound<'py, PyAny>,
        tracked: Bound<'py, PyAny>,
        retention: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        native(
            self.runtime.py(),
            NativeAttr::OldNameViewSkipReason,
            &[
                ("origin", origin.clone()),
                ("origin_tracked", tracked),
                ("retention", retention.clone()),
                (
                    "models",
                    PyTuple::new(self.runtime.py(), &self.models)?.into_any(),
                ),
                ("views", self.views.clone()),
            ],
        )
    }

    fn aliases(&self, item: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        let py = self.runtime.py();
        if !stores_history(item)? {
            return registry::native(py, NativeAttr::DeclaredColumnAliases)?.call1((item,));
        }
        let mut aliases: Vec<Bound<'py, PyTuple>> = Vec::new();
        for entry in self.columns.try_iter()? {
            let entry = entry?;
            let decision = entry.getattr("decision")?;
            if entry.getattr("model_name")?.eq(item.getattr("name")?)?
                && (decision.eq("rename")? || decision.eq("record")?)
            {
                aliases.push(PyTuple::new(
                    py,
                    [
                        entry.getattr("origin_column")?,
                        entry.getattr("destination_column")?,
                    ],
                )?);
            }
        }
        let aliases = PyList::new(py, aliases)?;
        aliases.call_method0("sort")?;
        imported(py, "builtins", "tuple")?.call1((aliases,))
    }

    fn new_move(
        &self,
        entry: &Bound<'py, PyAny>,
        item: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let py = self.runtime.py();
        let retention = retention(item, &self.retention)?;
        let reason = self.skip(
            &entry.getattr("origin")?,
            entry.getattr("origin_tracked")?,
            &retention,
        )?;
        let mut fields = vec![
            ("model_name", entry.getattr("model_name")?),
            ("origin", entry.getattr("origin")?),
            ("destination", entry.getattr("destination")?),
            ("target_name", entry.getattr("target_name")?),
        ];
        if !reason.is_none() || retention.is_none() {
            fields.extend([
                ("action", action(&self.runtime, "NONE")?),
                (
                    "reason",
                    if reason.is_truthy()? {
                        reason
                    } else {
                        text(py, "old_name_view false")
                    },
                ),
            ]);
        } else {
            fields.extend([
                ("action", action(&self.runtime, "ARCHIVE_AND_VIEW")?),
                ("expires_at", expires(&retention, &self.now)?),
                ("retention", retention),
                ("column_aliases", self.aliases(item)?),
                (
                    "stores_history",
                    PyBool::new(py, stores_history(item)?).to_owned().into_any(),
                ),
                (
                    "records_requirement",
                    PyBool::new(py, true).to_owned().into_any(),
                ),
                (
                    "grants_supported",
                    self.runtime
                        .getattr("adapter")?
                        .getattr("relation_grants_supported")?,
                ),
            ]);
        }
        model(py, RecordId::OldNameViewPlanEntry, &fields)
    }

    fn resume(
        &self,
        history: &Bound<'py, PyAny>,
        item: &Bound<'py, PyAny>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        let py = self.runtime.py();
        let status: String =
            call_with(&history.getattr("status")?, &[("now", self.now.clone())])?.extract()?;
        let action_name = match status.as_str() {
            "pending_archive" => "ARCHIVE_AND_VIEW",
            "pending_view" => "VIEW_ONLY",
            "live" | "expired" => "LIVE",
            _ => return Ok(None),
        };
        if status == PENDING_ARCHIVE || status == PENDING_VIEW {
            let reason = self.skip(
                &location(&self.runtime, &history.getattr("old")?)?,
                py.None().into_bound(py),
                &retention(item, &self.retention)?,
            )?;
            if !reason.is_none() {
                return model(
                    py,
                    RecordId::OldNameViewPlanEntry,
                    &[
                        (
                            "model_name",
                            history.getattr("move")?.getattr("destination_model")?,
                        ),
                        ("origin", location(&self.runtime, &history.getattr("old")?)?),
                        (
                            "destination",
                            location(&self.runtime, &history.getattr("new")?)?,
                        ),
                        ("action", action(&self.runtime, "NONE")?),
                        (
                            "target_name",
                            history.getattr("move")?.getattr("target_name")?,
                        ),
                        (
                            "migration_event_id",
                            history.getattr("move")?.getattr("event_id")?,
                        ),
                        ("reason", reason),
                    ],
                )
                .map(Some);
            }
        }
        let retention = history.getattr("required")?.getattr("view_retention")?;
        let duration = registry::class(py, RecordId::Duration)?.call_method1(
            "parse",
            (if retention.is_truthy()? {
                retention.clone()
            } else {
                text(py, "")
            },),
        )?;
        let created = history.getattr("created")?;
        let expires_at = if !created.is_none() {
            created.getattr("expires_at")?
        } else if duration.is_none() {
            py.None().into_bound(py)
        } else {
            duration.call_method1("add_to", (&self.now,))?
        };
        let grants = if created.is_none() {
            py.None().into_bound(py)
        } else {
            created.getattr("grants_copied")?
        };
        model(
            py,
            RecordId::OldNameViewPlanEntry,
            &[
                ("model_name", item.getattr("name")?),
                ("origin", location(&self.runtime, &history.getattr("old")?)?),
                (
                    "destination",
                    location(&self.runtime, &history.getattr("new")?)?,
                ),
                ("action", action(&self.runtime, action_name)?),
                (
                    "target_name",
                    history.getattr("move")?.getattr("target_name")?,
                ),
                ("retention", retention),
                ("expires_at", expires_at),
                (
                    "column_aliases",
                    if created.is_none() {
                        self.aliases(item)?
                    } else {
                        created.getattr("column_aliases")?
                    },
                ),
                (
                    "stores_history",
                    PyBool::new(py, stores_history(item)?).to_owned().into_any(),
                ),
                (
                    "migration_event_id",
                    history.getattr("move")?.getattr("event_id")?,
                ),
                (
                    "grants_copied",
                    if grants.is_none() {
                        grants
                    } else {
                        imported(py, "builtins", "len")?.call1((grants,))?
                    },
                ),
                (
                    "grants_supported",
                    self.runtime
                        .getattr("adapter")?
                        .getattr("relation_grants_supported")?,
                ),
                (
                    "archived",
                    PyBool::new(py, !history.getattr("archived")?.is_none())
                        .to_owned()
                        .into_any(),
                ),
            ],
        )
        .map(Some)
    }
}

fn action<'py>(runtime: &Bound<'py, PyAny>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    registry::class(runtime.py(), RecordId::OldNameViewAction)?.getattr(name)
}
