//! Which tests and scenarios a `--since` run selects, and why, from what each really executes.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::Path;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_analysis::definition_changes::constants::{
    MACRO_KIND, MODEL_KIND, SCENARIO_KIND, SEED_KIND, TABLE_FUNCTION_KIND, TEST_FILE_KIND,
};
use sqlbuild_analysis::definition_changes::main::changes_summary::changes_summary;
use sqlbuild_analysis::definition_changes::main::compare_definitions::compare_definitions;
use sqlbuild_analysis::definition_changes::main::node_key::node_key;
use sqlbuild_analysis::definition_changes::main::selection_reasons::selection_reasons;
use sqlbuild_analysis::definition_changes::main::selection_report::selection_report;
use sqlbuild_analysis::definition_changes::models::{
    DefinitionChanges, DefinitionSnapshot, ExecutedItem, SelectedItem,
};

use crate::bindings::_helpers::change_selection::base_snapshot::BaseComparison;
use crate::bindings::_helpers::change_selection::definition_snapshot::{
    declaration_uses, definition_snapshot,
};
use crate::bindings::_helpers::compiled_views::model_reads;
use crate::bindings::_helpers::compiled_views::project_reads;
use crate::bindings::_helpers::graph::keys::native_key;
use crate::bindings::_helpers::planner_scenario::graph::plan_scenario_graph;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::scenario_command::setup::{flush, write};

const MACRO_TEST_MODE: &str = "macro";
const TEST_CONSUMER_KIND: &str = "test";

/// The changes since the base revision and what the current revision uses.
pub(crate) struct ChangedProject {
    pub(crate) reference: String,
    pub(crate) current: DefinitionSnapshot,
    pub(crate) changes: DefinitionChanges,
    uses: BTreeMap<String, BTreeSet<String>>,
}

/// Compare the compiled working tree `project` with the base snapshot.
pub(crate) fn changed_project(
    project: &Bound<'_, PyAny>,
    project_dir: &Path,
    base: BaseComparison,
) -> PyResult<ChangedProject> {
    let current: DefinitionSnapshot = definition_snapshot(project, project_dir)?;
    let changes: DefinitionChanges = compare_definitions(&base.snapshot, &current);
    Ok(ChangedProject {
        reference: base.base.reference,
        current,
        changes,
        uses: declaration_uses(project)?,
    })
}

fn strings(value: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    value.try_iter()?.map(|item| item?.extract()).collect()
}

impl ChangedProject {
    /// Keys of current nodes of `kind` named in `names`.
    fn keys_named(&self, kind: &str, names: &[String]) -> BTreeSet<String> {
        self.current
            .nodes
            .iter()
            .filter(|(_, node)| node.kind == kind && names.contains(&node.name))
            .map(|(key, _)| key.clone())
            .collect()
    }

    fn declarations_of(&self, consumer: &str) -> Vec<String> {
        self.uses
            .get(consumer)
            .into_iter()
            .flatten()
            .cloned()
            .collect()
    }

    /// Why `item` is affected; empty when nothing it runs changed.
    pub(crate) fn reasons(&self, item: &ExecutedItem) -> Vec<String> {
        selection_reasons(item, &self.current, &self.changes)
    }

    /// Write the change summary and the selection to `stream`.
    pub(crate) fn report(
        &self,
        stream: &Bound<'_, PyAny>,
        nouns: (&str, &str),
        (total, selected, explain): (usize, &[SelectedItem], bool),
    ) -> PyResult<()> {
        write(
            stream,
            &selection_report(
                (&self.reference, &changes_summary(&self.changes)),
                nouns,
                (total, selected),
                explain,
            ),
        )?;
        flush(stream)
    }

    /// What one planned unit test executes, honouring its mocks.
    pub(crate) fn test_item(
        &self,
        entry: &Bound<'_, PyAny>,
        (tests, models): (
            &HashMap<String, Bound<'_, PyAny>>,
            &HashMap<String, Bound<'_, PyAny>>,
        ),
    ) -> PyResult<ExecutedItem> {
        let name: String = native_field(entry, "name")?.extract()?;
        let mut item: ExecutedItem = ExecutedItem {
            declarations: self.declarations_of(&node_key(TEST_CONSUMER_KIND, &name)),
            ..ExecutedItem::default()
        };
        let mocked_seeds: Vec<String> = strings(&native_field(entry, "mock_seed_names")?)?;
        let mocked_functions: Vec<String> =
            strings(&native_field(entry, "mock_table_function_names")?)?;
        item.mocked
            .extend(self.keys_named(TABLE_FUNCTION_KIND, &mocked_functions));
        if let Some(test) = tests.get(&name) {
            let file: Bound<'_, PyAny> = native_field(test, "test_file")?;
            item.own_keys.push(node_key(
                TEST_FILE_KIND,
                &native_field(&file, "relative_path")?
                    .str()?
                    .to_string()
                    .replace('\\', "/"),
            ));
            let payload: Bound<'_, PyAny> = native_field(test, "payload")?;
            if let Ok(mocks) = native_field(&payload, "macro_mocks")
                && let Ok(mocks) = mocks.cast::<PyDict>()
            {
                let names: Vec<String> = mocks
                    .iter()
                    .map(|(key, _)| key.extract())
                    .collect::<PyResult<_>>()?;
                item.mocked.extend(self.keys_named(MACRO_KIND, &names));
            }
            if let Ok(mode) = native_field(&payload, "mode")
                && native_field(&mode, "value")?.extract::<String>()? == MACRO_TEST_MODE
            {
                let tested: Vec<String> =
                    strings(&native_field(&payload, "tested_resource_names")?)?;
                item.declarations
                    .extend(self.keys_named(MACRO_KIND, &tested));
            }
        }
        for step in native_field(entry, "chain")?.try_iter()? {
            let model_name: String = native_field(&step?, "model_name")?.extract()?;
            item.executed.push(node_key(MODEL_KIND, &model_name));
            let Some(model) = models.get(&model_name) else {
                continue;
            };
            for dependency in model_reads::deps(model)?.try_iter()? {
                let (kind, dependency_name) = native_key(&dependency?)?;
                if kind == SEED_KIND && !mocked_seeds.contains(&dependency_name) {
                    item.executed.push(node_key(SEED_KIND, &dependency_name));
                }
            }
        }
        for key in native_field(entry, "function_deps")?.try_iter()? {
            let (kind, function_name) = native_key(&key?)?;
            item.executed.push(node_key(&kind, &function_name));
        }
        Ok(item)
    }

    /// What one compiled scenario builds and loads, honouring its fixtures.
    pub(crate) fn scenario_item(
        &self,
        scenario: &Bound<'_, PyAny>,
        project: &Bound<'_, PyAny>,
    ) -> PyResult<ExecutedItem> {
        let name: String = native_field(scenario, "name")?.extract()?;
        let key: String = node_key(SCENARIO_KIND, &name);
        let (graph, _) = plan_scenario_graph(scenario, project, true, None)?;
        let mut item: ExecutedItem = ExecutedItem {
            own_keys: vec![key.clone()],
            declarations: self.declarations_of(&key),
            ..ExecutedItem::default()
        };
        for model_name in strings(&native_field(&graph, "model_names")?)? {
            item.executed.push(node_key(MODEL_KIND, &model_name));
        }
        let fixtures: Vec<String> = strings(&native_field(&graph, "seed_fixture_names")?)?;
        for seed_name in strings(&native_field(&graph, "seed_names")?)? {
            if !fixtures.contains(&seed_name) {
                item.executed.push(node_key(SEED_KIND, &seed_name));
            }
        }
        for function in native_field(&graph, "function_deps")?.try_iter()? {
            let (kind, function_name) = native_key(&function?)?;
            item.executed.push(node_key(&kind, &function_name));
        }
        Ok(item)
    }
}

/// The project's compiled tests and models by name.
pub(crate) fn tests_and_models<'py>(
    project: &Bound<'py, PyAny>,
) -> PyResult<(
    HashMap<String, Bound<'py, PyAny>>,
    HashMap<String, Bound<'py, PyAny>>,
)> {
    let mut tests: HashMap<String, Bound<'py, PyAny>> = HashMap::new();
    for test in project_reads::sql_tests(project)?.try_iter()? {
        let test: Bound<'py, PyAny> = test?;
        tests.insert(native_field(&test, "name")?.extract()?, test);
    }
    let mut models: HashMap<String, Bound<'py, PyAny>> = HashMap::new();
    for model in project_reads::models(project)?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        models.insert(model_reads::model_name(&model)?, model);
    }
    Ok((tests, models))
}
