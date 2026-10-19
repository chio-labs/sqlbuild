use std::collections::{HashMap, HashSet};

use crate::planner_fixtures::main::align_columns::align_columns;
use crate::planner_fixtures::main::required_columns::required_columns;
use crate::planner_fixtures::models::{
    AlignmentInput, FixtureColumn, FixtureReadCache, FixtureReadKey, FixtureReadModel,
    FixtureReadSchemas, FixtureStarRelation,
};
use crate::planner_fixtures::tests::helpers::column;
use crate::planner_fixtures::tests::test_types::RequiredColumnsTestCase;
use crate::required_columns::models::ColumnRead;

#[test]
fn given_star_and_differently_cased_reads_when_requiring_then_each_column_is_required_once() {
    let test_cases = [
        RequiredColumnsTestCase {
            description: "upper-case reads through a star import",
            reads: &["ORDER_ID", "STATUS"],
            star: true,
            expected_required: &["ORDER_ID", "STATUS", "customer_id"],
            expected_completed: &[1, 2],
        },
        RequiredColumnsTestCase {
            description: "same-case reads through a star import",
            reads: &["order_id", "status"],
            star: true,
            expected_required: &["order_id", "status", "customer_id"],
            expected_completed: &[1, 2],
        },
        RequiredColumnsTestCase {
            description: "upper-case reads without a star",
            reads: &["ORDER_ID", "STATUS", "Status"],
            star: false,
            expected_required: &["ORDER_ID", "STATUS"],
            expected_completed: &[2],
        },
    ];
    let key = ("source".to_owned(), "orders".to_owned());
    let metadata = vec![
        column("order_id", "VARCHAR", true),
        column("customer_id", "VARCHAR", true),
        column("status", "VARCHAR", true),
    ];
    let keys = HashSet::from([key.clone()]);
    let authoritative = HashMap::from([(
        key.clone(),
        metadata
            .iter()
            .map(|column| column.folded_name.clone())
            .collect::<HashSet<_>>(),
    )]);
    let relations = [FixtureStarRelation {
        key: key.clone(),
        columns: metadata.clone(),
        authoritative: true,
    }];
    for test_case in test_cases {
        let models = [FixtureReadModel {
            name: "orders_report".into(),
            key: FixtureReadKey {
                sql: String::new(),
                references: Vec::new(),
                dialect: Some("snowflake".into()),
            },
            high_confidence: test_case
                .reads
                .iter()
                .map(|name| ColumnRead {
                    resource_type: key.0.clone(),
                    resource_name: key.1.clone(),
                    column_name: (*name).into(),
                })
                .collect(),
            stars: test_case.star.then(|| key.clone()).into_iter().collect(),
        }];
        let (_, result) = required_columns(
            FixtureReadCache::default(),
            &models,
            FixtureReadSchemas {
                keys: &keys,
                authoritative: &authoritative,
                relations: &relations,
            },
        );
        let requirements = result.expect(test_case.description);
        let required = &requirements.columns[0].1;
        let names: Vec<&str> = required.iter().map(|column| column.name.as_str()).collect();
        assert_eq!(
            names, test_case.expected_required,
            "{}",
            test_case.description
        );
        let supplied = [FixtureColumn {
            name: "order_id".into(),
            folded_name: "order_id".into(),
            sql_type: None,
            nullable: None,
        }];
        let alignment = align_columns(
            "mock source 'orders'",
            AlignmentInput {
                supplied: &supplied,
                metadata: &metadata,
                required,
                star: test_case.star,
                typed_nulls: false,
            },
        );
        assert_eq!(
            alignment.completed.as_deref(),
            Some(test_case.expected_completed),
            "{}",
            test_case.description
        );
    }
}
