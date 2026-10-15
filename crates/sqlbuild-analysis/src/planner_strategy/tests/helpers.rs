use std::collections::BTreeMap;

use crate::planner_changes::models::{SchemaChangeKind, SchemaColumnSource, SchemaFindingRow};
use crate::planner_strategy::errors::LineageFailure;
use crate::planner_strategy::models::{
    ChangeFacts, CursorInputColumnCheck, CursorInputColumnOwner, LookbackConfig, PlanChangeKind,
    ProducerFacts, ReferenceIdentity, WarningRow, WarningSeverity,
};
use crate::planner_strategy::tests::test_types::{Lineage, Steps};
use crate::planner_strategy::types::{ReferenceGraph, Timeline};

pub(super) fn change(kind: PlanChangeKind) -> ChangeFacts {
    ChangeFacts {
        kind,
        backfill_full: false,
        backfill_forward_only: true,
        query_changed: kind == PlanChangeKind::QueryChanged,
        changed_functions: Vec::new(),
        config_changed: false,
        schema_findings: Vec::new(),
        recorded_build_relation_missing: false,
    }
}

pub(super) fn finding(
    kind: SchemaChangeKind,
    source: SchemaColumnSource,
    (expected_type, actual_type): (Option<&str>, Option<&str>),
) -> SchemaFindingRow {
    SchemaFindingRow {
        kind,
        column_name: "amount".to_owned(),
        source,
        expected_type: expected_type.map(str::to_owned),
        actual_type: actual_type.map(str::to_owned),
    }
}

pub(super) fn warning(severity: WarningSeverity, message: &str) -> WarningRow {
    WarningRow {
        severity,
        message: message.to_owned(),
        code: None,
    }
}

pub(super) fn names(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| (*item).to_owned()).collect()
}

impl Timeline for Steps {
    type Moment = i64;
    type Error = ();

    fn advance(&self, moment: &i64) -> Result<i64, ()> {
        Ok(moment + 3)
    }

    fn precedes(&self, left: &i64, right: &i64) -> Result<bool, ()> {
        Ok(left < right)
    }
}

fn reference(kind: &str, name: &str) -> ReferenceIdentity {
    ReferenceIdentity {
        kind: kind.to_owned(),
        name: name.to_owned(),
    }
}

impl Lineage {
    pub(super) fn roots() -> Vec<ReferenceIdentity> {
        vec![reference("ref", "customers"), reference("udf", "discount")]
    }
}

impl ReferenceGraph for Lineage {
    type Reference = ReferenceIdentity;
    type Error = ();

    fn identity(&self, reference: &ReferenceIdentity) -> Result<ReferenceIdentity, ()> {
        Ok(reference.clone())
    }

    fn model_references(&self, name: &str) -> Result<Option<Vec<ReferenceIdentity>>, ()> {
        let models: BTreeMap<&str, Vec<ReferenceIdentity>> = BTreeMap::from([
            ("customers", vec![reference("ref", "events")]),
            ("events", vec![reference("source", "raw_events")]),
            ("products", Vec::new()),
        ]);
        Ok(models.get(name).cloned())
    }

    fn function_references(&self, name: &str) -> Result<Option<Vec<ReferenceIdentity>>, ()> {
        Ok((name == "discount").then(|| vec![reference("ref", "products")]))
    }

    fn producer_facts(&self, name: &str) -> Result<ProducerFacts, ()> {
        Ok(ProducerFacts {
            microbatch: name == "customers" || self.capped.contains(name),
            capped: self.capped.contains(name),
        })
    }

    fn watermark_inputs(&self, name: &str) -> Result<Vec<String>, ()> {
        Ok(if name == "customers" {
            names(&["events"])
        } else {
            Vec::new()
        })
    }
}

pub(super) fn failure_text(failure: LineageFailure<()>) -> String {
    format!("{failure:?}")
}

pub(super) fn column_check(
    owner: CursorInputColumnOwner,
    known: &[&str],
) -> CursorInputColumnCheck {
    CursorInputColumnCheck {
        model_name: "daily_orders".to_owned(),
        owner,
        input_name: "orders".to_owned(),
        column: "Updated_At".to_owned(),
        known_columns: known.iter().map(|name| (*name).to_owned()).collect(),
    }
}

pub(super) fn lookback_config(
    lookback: Option<&str>,
    strategy: Option<&str>,
    grain: Option<&str>,
) -> LookbackConfig {
    LookbackConfig {
        lookback: lookback.map(str::to_owned),
        incremental_strategy: strategy.map(str::to_owned),
        batch_size: Some("effective".to_owned()),
        grain: grain.map(str::to_owned),
    }
}
