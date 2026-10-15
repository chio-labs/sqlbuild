use crate::cost_allocation::_helpers::decimal::{from_float, integer, parse};
use crate::cost_allocation::models::{CostQuery, PyDecimal, WarehouseKey};

pub(crate) fn decimal(text: &str) -> PyDecimal {
    parse(text).unwrap_or_else(|| integer(0))
}

pub(crate) fn float(value: f64) -> PyDecimal {
    from_float(value).unwrap_or_else(|| integer(0))
}

pub(crate) fn query(index: u64) -> CostQuery {
    CostQuery {
        query_id: format!("q{index}"),
        warehouse: WarehouseKey {
            name: "WH".to_owned(),
            size: "X-SMALL".to_owned(),
            kind: Some("STANDARD".to_owned()),
            cluster: Some(1),
        },
        started_micros: 0,
        completed_micros: 1_000_000,
        in_run: true,
        resource_type: Some("model".to_owned()),
        resource_name: Some("orders".to_owned()),
        bytes_scanned: 1,
    }
}
