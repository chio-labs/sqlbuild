//! `allocate_run_cost`: share each warehouse's busy time equally among concurrently active queries.

use std::collections::{BTreeSet, HashMap};

use crate::cost_allocation::_helpers::allocation::{
    attributed_seconds, credits_per_hour, grouped, resource_allocation, resource_order, sum,
};
use crate::cost_allocation::_helpers::decimal::integer;
use crate::cost_allocation::constants::{
    RESULT_LIMIT_LIMITATION, STANDARD_WAREHOUSE_TYPE, UNKNOWN_RESOURCE,
};
use crate::cost_allocation::models::{
    AllocationStatus, CostQuery, PyDecimal, ResourceAllocation, RunAllocation, WarehouseKey,
};

/// Attribute the run's share of busy warehouse time and price it; pending without run queries.
pub fn allocate_run_cost(
    queries: &[CostQuery],
    usd_per_credit: &PyDecimal,
    result_limit_reached: bool,
) -> RunAllocation {
    let run_queries: Vec<&CostQuery> = queries.iter().filter(|query| query.in_run).collect();
    if run_queries.is_empty() {
        return RunAllocation {
            status: AllocationStatus::Pending,
            resources: Vec::new(),
            query_count: 0,
            attributed_seconds: integer(0),
            bytes_scanned: 0,
            estimated_compute_credits: integer(0),
            estimated_usd: integer(0),
            limitations: Vec::new(),
        };
    }
    let attributed: HashMap<String, PyDecimal> = attributed_seconds(queries);
    let mut limitations: Vec<String> = Vec::new();
    let mut resources: Vec<ResourceAllocation> = Vec::new();
    for (key, group) in grouped(run_queries.iter().copied(), |query| {
        (
            query
                .resource_type
                .clone()
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| UNKNOWN_RESOURCE.to_owned()),
            query
                .resource_name
                .clone()
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| UNKNOWN_RESOURCE.to_owned()),
            query.warehouse.clone(),
        )
    }) {
        let warehouse: &WarehouseKey = &key.2;
        let rate: Option<u64> = credits_per_hour(&warehouse.size);
        match &warehouse.kind {
            None => limitations.push(format!("Unknown warehouse type for {}", warehouse.name)),
            Some(kind) if kind.to_uppercase() != STANDARD_WAREHOUSE_TYPE => {
                limitations.push(format!("Unsupported Snowflake warehouse type: {kind}"));
                continue;
            }
            Some(_) => {}
        }
        if warehouse.cluster.is_none() {
            limitations.push(format!("Unknown cluster number for {}", warehouse.name));
        }
        let Some(rate) = rate else {
            limitations.push(format!(
                "Unknown Snowflake warehouse size: {}",
                warehouse.size
            ));
            continue;
        };
        resources.push(resource_allocation(
            key,
            &group,
            (&attributed, rate, usd_per_credit),
        ));
    }
    if result_limit_reached {
        limitations.push(RESULT_LIMIT_LIMITATION.to_owned());
    }
    resources.sort_by(resource_order);
    let limitations: Vec<String> = limitations
        .into_iter()
        .collect::<BTreeSet<String>>()
        .into_iter()
        .collect();
    RunAllocation {
        status: if limitations.is_empty() {
            AllocationStatus::Complete
        } else {
            AllocationStatus::Partial
        },
        query_count: run_queries.len(),
        attributed_seconds: sum(resources.iter().map(|item| &item.attributed_seconds)),
        bytes_scanned: resources.iter().map(|item| item.bytes_scanned).sum(),
        estimated_compute_credits: sum(resources
            .iter()
            .map(|item| &item.estimated_compute_credits)),
        estimated_usd: sum(resources.iter().map(|item| &item.estimated_usd)),
        limitations,
        resources,
    }
}
