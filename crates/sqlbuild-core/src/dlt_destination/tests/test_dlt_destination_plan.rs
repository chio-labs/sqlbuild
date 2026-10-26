//! dlt destination calls match the Python integration's.

use crate::dlt_destination::main::dlt_destination_plan::dlt_destination_plan;
use crate::dlt_destination::models::{
    DltDataset, DltDatasetName, DltDestinationPlan, DltDestinationRequest, DltValue,
};
use crate::dlt_destination::tests::test_types::DestinationPlanTestCase;
use crate::loader_connection::models::LoaderConnection;

#[test]
fn given_adapter_connection_when_planning_dlt_destination_then_matches_python_mapping() {
    let test_cases = [
        DestinationPlanTestCase {
            description: "duckdb without dataset lands in main",
            adapter: "duckdb",
            strings: &[("database", " warehouse.duckdb ")],
            port: None,
            destination_keys: &[],
            dataset_name: None,
            expected_plan: Ok(DltDestinationPlan {
                factory: "duckdb",
                arguments: vec![("credentials", DltValue::Text("warehouse.duckdb".to_owned()))],
                dataset: DltDataset::Default("main"),
            }),
        },
        DestinationPlanTestCase {
            description: "sqlite writes its database file through sqlalchemy into main",
            adapter: "sqlite",
            strings: &[("path", "/data/warehouse.sqlite")],
            port: None,
            destination_keys: &[],
            dataset_name: None,
            expected_plan: Ok(DltDestinationPlan {
                factory: "sqlalchemy",
                arguments: vec![(
                    "credentials",
                    DltValue::Text("sqlite:////data/warehouse.sqlite".to_owned()),
                )],
                dataset: DltDataset::Default("main"),
            }),
        },
        DestinationPlanTestCase {
            description: "postgres connection string uses host default and port",
            adapter: "postgres",
            strings: &[("user", "u"), ("database", "d")],
            port: Some("6543"),
            destination_keys: &["staging"],
            dataset_name: Some("raw"),
            expected_plan: Ok(DltDestinationPlan {
                factory: "postgres",
                arguments: vec![(
                    "credentials",
                    DltValue::Text("postgresql://u:@localhost:6543/d".to_owned()),
                )],
                dataset: DltDataset::Given,
            }),
        },
        DestinationPlanTestCase {
            description: "owned destination keys are sorted in the error",
            adapter: "postgres",
            strings: &[],
            port: None,
            destination_keys: &["dataset_name", "credentials"],
            dataset_name: Some("raw"),
            expected_plan: Err(
                "Adapter 'postgres' dlt destination config cannot define SQLBuild-owned key(s): credentials, dataset_name",
            ),
        },
        DestinationPlanTestCase {
            description: "blank dataset is rejected before credentials",
            adapter: "snowflake",
            strings: &[],
            port: None,
            destination_keys: &[],
            dataset_name: Some(" "),
            expected_plan: Err(
                "Adapter 'snowflake' requires an explicit dlt source schema for raw landing",
            ),
        },
        DestinationPlanTestCase {
            description: "missing required setting names the dlt loader",
            adapter: "snowflake",
            strings: &[],
            port: None,
            destination_keys: &[],
            dataset_name: Some("raw"),
            expected_plan: Err(
                "Adapter 'snowflake' requires connection.account for dlt integration loaders",
            ),
        },
    ];

    for test_case in test_cases {
        let connection = LoaderConnection {
            strings: test_case
                .strings
                .iter()
                .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
                .collect(),
            port: test_case.port.map(str::to_owned),
        };
        let destination_keys: Vec<Option<String>> = test_case
            .destination_keys
            .iter()
            .map(|key| Some((*key).to_owned()))
            .collect();
        let dataset_name = DltDatasetName {
            text: test_case.dataset_name.map(str::to_owned),
            truthy: test_case.dataset_name.is_some_and(|name| !name.is_empty()),
        };
        let request = DltDestinationRequest {
            adapter: test_case.adapter,
            connection: &connection,
            destination_keys: &destination_keys,
            dataset_name: &dataset_name,
        };
        assert_eq!(
            dlt_destination_plan(&request).map_err(|error| error.message),
            test_case.expected_plan.map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
