use serde_json::json;
use tempfile::TempDir;

use crate::engine::tests::{helpers, test_types};

#[test]
fn given_owner_and_declaration_layouts_when_evaluating_then_returns_expected_faults()
-> Result<(), String> {
    let oversized_paths: Vec<String> = (0..11)
        .map(|index| format!("models/race/_macros/item_{index}.py"))
        .collect();
    let test_cases = [
        test_types::DomainLayoutTestCase {
            description: "leaf and branch models fault",
            code: "SQBKR501",
            models: json!([
                helpers::model("models/race/mart/summary.sql"),
                helpers::model("models/race/mart/horses/model.sql")
            ]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_index(),
            expected_codes: &["SQBKR501"],
            expected_message_fragments: &["mixes direct model"],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "default owner depth faults",
            code: "SQBKR502",
            models: json!([helpers::model(
                "models/race/intermediate/enriched/horse/clusters_resolved/model.sql"
            )]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_index(),
            expected_codes: &["SQBKR502"],
            expected_message_fragments: &["configured maximum is 1"],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "configured owner depth passes",
            code: "SQBKR502",
            models: json!([helpers::model(
                "models/race/intermediate/enriched/horse/clusters_resolved/model.sql"
            )]),
            thresholds: json!({"max_subdomain_depth": 2}),
            layout: json!({}),
            scope_index: helpers::scope_index(),
            expected_codes: &[],
            expected_message_fragments: &[],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "longest unary owner prefix faults",
            code: "SQBKR503",
            models: json!([
                helpers::model("models/race/mart/barrier_trial/model.sql"),
                helpers::model("models/race/mart/barrier_trial_analysis/model.sql")
            ]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_index(),
            expected_codes: &["SQBKR503"],
            expected_message_fragments: &["barrier_trial"],
            expected_absent_fragments: &["bucket \"barrier\""],
        },
        test_types::DomainLayoutTestCase {
            description: "each branching owner prefix faults",
            code: "SQBKR503",
            models: json!([
                helpers::model("models/crm/mart/salesforce_annotation_export/model.sql"),
                helpers::model("models/crm/mart/salesforce_annotation_validation/model.sql"),
                helpers::model("models/crm/mart/salesforce_events/model.sql")
            ]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_index(),
            expected_codes: &["SQBKR503", "SQBKR503"],
            expected_message_fragments: &["salesforce\"", "salesforce_annotation"],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "mixed declaration container faults",
            code: "SQBKH301",
            models: json!([]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_with_macros(&[
                "models/race/_macros/direct.py".into(),
                "models/race/_macros/scoring/grouped.py".into(),
            ]),
            expected_codes: &["SQBKH301"],
            expected_message_fragments: &[],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "nested declaration bucket faults",
            code: "SQBKH302",
            models: json!([]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_with_macros(&[
                "models/race/_macros/scoring/candidates/item.py".into(),
            ]),
            expected_codes: &["SQBKH302"],
            expected_message_fragments: &[],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "oversized flat declaration container faults",
            code: "SQBKH303",
            models: json!([]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_with_macros(&oversized_paths),
            expected_codes: &["SQBKH303"],
            expected_message_fragments: &[],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "generic declaration bucket faults",
            code: "SQBKH304",
            models: json!([]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_with_macros(&["models/race/_macros/utils/item.py".into()]),
            expected_codes: &["SQBKH304"],
            expected_message_fragments: &[],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "shared declaration filename prefix faults",
            code: "SQBKH305",
            models: json!([]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_with_macros(&[
                "models/race/_macros/normalise_horse.py".into(),
                "models/race/_macros/normalise_person.py".into(),
            ]),
            expected_codes: &["SQBKH305"],
            expected_message_fragments: &["normalise"],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "model outside configured levels faults",
            code: "SQBKR500",
            models: json!([helpers::model("models/race/unknown/model.sql")]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_index(),
            expected_codes: &["SQBKR500"],
            expected_message_fragments: &["does not resolve"],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "implicit domain grouping prefix faults",
            code: "SQBKR503",
            models: json!([
                helpers::model("models/salesforce_annotation_export/mart/model.sql"),
                helpers::model("models/salesforce_annotation_validation/mart/model.sql")
            ]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_index(),
            expected_codes: &["SQBKR503"],
            expected_message_fragments: &["salesforce_annotation"],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "ambiguous inferred domain root faults",
            code: "SQBKR500",
            models: json!([helpers::model("models/race/staging/mart/model.sql")]),
            thresholds: json!({}),
            layout: json!({}),
            scope_index: helpers::scope_index(),
            expected_codes: &["SQBKR500"],
            expected_message_fragments: &["ambiguous"],
            expected_absent_fragments: &[],
        },
        test_types::DomainLayoutTestCase {
            description: "explicit nested domain root resolves",
            code: "SQBKR500",
            models: json!([helpers::model("models/market/betfair/mart/core/model.sql")]),
            thresholds: json!({}),
            layout: json!({"levels": ["mart"], "domain_roots": ["market/betfair"]}),
            scope_index: helpers::scope_index(),
            expected_codes: &[],
            expected_message_fragments: &[],
            expected_absent_fragments: &[],
        },
    ];

    for test_case in test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let result = helpers::domain_layout_evaluation(
            &project_dir,
            test_case.code,
            test_case.models,
            test_case.thresholds,
            test_case.layout,
            test_case.scope_index,
        )?;
        let faults = result["faults"]
            .as_array()
            .ok_or_else(|| "faults must be an array".to_owned())?;
        let codes: Vec<&str> = faults
            .iter()
            .filter_map(|fault| fault["code"].as_str())
            .collect();
        let messages = faults
            .iter()
            .filter_map(|fault| fault["message"].as_str())
            .collect::<Vec<_>>()
            .join("\n");

        assert_eq!(codes, test_case.expected_codes, "{}", test_case.description);
        for fragment in test_case.expected_message_fragments {
            assert!(messages.contains(fragment), "{}", test_case.description);
        }
        for fragment in test_case.expected_absent_fragments {
            assert!(!messages.contains(fragment), "{}", test_case.description);
        }
    }
    Ok(())
}
