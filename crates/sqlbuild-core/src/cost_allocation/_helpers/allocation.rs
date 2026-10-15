//! Busy-time attribution, warehouse rates, totals and ordering of priced resources.

use std::cmp::Ordering;
use std::collections::{BTreeSet, HashMap};

use crate::cost_allocation::_helpers::decimal::{
    add, compare, divide, from_float, integer, multiply,
};
use crate::cost_allocation::constants::{CREDITS_PER_HOUR, MICROS_PER_SECOND, SECONDS_PER_HOUR};
use crate::cost_allocation::models::{CostQuery, PyDecimal, ResourceAllocation};
use crate::cost_allocation::types::ResourceKey;

/// Items grouped by key in first-appearance order, as a Python `defaultdict(list)`.
pub(crate) fn grouped<'a, K: Eq + std::hash::Hash + Clone>(
    items: impl Iterator<Item = &'a CostQuery>,
    key: impl Fn(&CostQuery) -> K,
) -> Vec<(K, Vec<&'a CostQuery>)> {
    let mut positions: HashMap<K, usize> = HashMap::new();
    let mut groups: Vec<(K, Vec<&'a CostQuery>)> = Vec::new();
    for item in items {
        let item_key: K = key(item);
        match positions.get(&item_key) {
            Some(&position) => groups[position].1.push(item),
            None => {
                positions.insert(item_key.clone(), groups.len());
                groups.push((item_key, vec![item]));
            }
        }
    }
    groups
}

/// Busy seconds attributed to each run query ID, accumulated in Python's iteration order.
pub(crate) fn attributed_seconds(queries: &[CostQuery]) -> HashMap<String, PyDecimal> {
    let mut attributed: HashMap<String, PyDecimal> = HashMap::new();
    for (_, warehouse_queries) in grouped(queries.iter(), |query| query.warehouse.clone()) {
        let boundaries: Vec<i128> = warehouse_queries
            .iter()
            .flat_map(|query| [query.started_micros, query.completed_micros])
            .collect::<BTreeSet<i128>>()
            .into_iter()
            .collect();
        for window in boundaries.windows(2) {
            let (start, end) = (window[0], window[1]);
            let active: Vec<&&CostQuery> = warehouse_queries
                .iter()
                .filter(|query| query.started_micros < end && query.completed_micros > start)
                .collect();
            if active.is_empty() {
                continue;
            }
            let elapsed: f64 = (end - start) as f64 / MICROS_PER_SECOND;
            let Some(elapsed) = from_float(elapsed) else {
                continue;
            };
            let share: PyDecimal = divide(&elapsed, active.len() as u64);
            for query in active.into_iter().filter(|query| query.in_run) {
                let total: PyDecimal = match attributed.get(&query.query_id) {
                    Some(total) => add(total, &share),
                    None => add(&integer(0), &share),
                };
                attributed.insert(query.query_id.clone(), total);
            }
        }
    }
    attributed
}

pub(crate) fn credits_per_hour(size: &str) -> Option<u64> {
    let size: String = size.to_uppercase();
    CREDITS_PER_HOUR
        .iter()
        .find(|(name, _)| *name == size)
        .map(|(_, rate)| *rate)
}

pub(crate) fn sum<'a>(values: impl Iterator<Item = &'a PyDecimal>) -> PyDecimal {
    values.fold(integer(0), |total, value| add(&total, value))
}

/// Python's sort key of a resource cost: most expensive first, then by identity.
pub(crate) fn resource_order(left: &ResourceAllocation, right: &ResourceAllocation) -> Ordering {
    let cluster = |resource: &ResourceAllocation| resource.warehouse.cluster.unwrap_or(-1);
    compare(&right.estimated_usd, &left.estimated_usd)
        .then_with(|| left.resource_name.cmp(&right.resource_name))
        .then_with(|| left.resource_type.cmp(&right.resource_type))
        .then_with(|| left.warehouse.name.cmp(&right.warehouse.name))
        .then_with(|| left.warehouse.size.cmp(&right.warehouse.size))
        .then_with(|| {
            left.warehouse
                .kind
                .as_deref()
                .unwrap_or("")
                .cmp(right.warehouse.kind.as_deref().unwrap_or(""))
        })
        .then_with(|| cluster(left).cmp(&cluster(right)))
}

pub(crate) fn resource_allocation(
    (resource_type, resource_name, warehouse): ResourceKey,
    queries: &[&CostQuery],
    (attributed, rate, usd_per_credit): (&HashMap<String, PyDecimal>, u64, &PyDecimal),
) -> ResourceAllocation {
    let zero: PyDecimal = integer(0);
    let seconds: PyDecimal = sum(queries
        .iter()
        .map(|query| attributed.get(&query.query_id).unwrap_or(&zero)));
    let credits: PyDecimal = divide(&multiply(&seconds, &integer(rate)), SECONDS_PER_HOUR);
    ResourceAllocation {
        resource_type,
        resource_name,
        warehouse,
        query_count: queries.len(),
        attributed_seconds: seconds,
        bytes_scanned: queries.iter().map(|query| query.bytes_scanned).sum(),
        estimated_usd: multiply(&credits, usd_per_credit),
        estimated_compute_credits: credits,
    }
}
