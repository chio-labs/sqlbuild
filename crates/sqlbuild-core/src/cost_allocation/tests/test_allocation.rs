use crate::cost_allocation::_helpers::decimal::text;
use crate::cost_allocation::main::allocate_run_cost::allocate_run_cost;
use crate::cost_allocation::models::{CostQuery, PyDecimal, RunAllocation};
use crate::cost_allocation::tests::helpers::query;
use crate::cost_allocation::tests::test_types::AllocationTestCase;

#[test]
fn given_concurrent_queries_when_allocating_then_shares_busy_seconds_equally() {
    let test_cases = [
        AllocationTestCase {
            description: "one query owns the whole second",
            concurrent_queries: 1,
            expected_seconds: "1.0",
            expected_usd: "0.0008333333333333333333333333334",
        },
        AllocationTestCase {
            description: "seven concurrent queries round each share",
            concurrent_queries: 7,
            expected_seconds: "1.000000000000000000000000000",
            expected_usd: "0.0008333333333333333333333333334",
        },
    ];

    for test_case in test_cases {
        let queries: Vec<CostQuery> = (0..test_case.concurrent_queries).map(query).collect();
        let rate: PyDecimal = PyDecimal {
            digits: vec![3, 0, 0],
            exponent: -2,
        };
        let allocation: RunAllocation = allocate_run_cost(&queries, &rate, false);

        assert_eq!(
            (
                text(&allocation.attributed_seconds),
                text(&allocation.estimated_usd),
            ),
            (
                test_case.expected_seconds.to_owned(),
                test_case.expected_usd.to_owned(),
            ),
            "{}",
            test_case.description
        );
    }
}
