use crate::compiled_project::main::plain_model_blocker::plain_model_blocker;
use crate::compiled_project::main::plain_model_facts::plain_model_facts;
use crate::compiled_project::models::{
    AnalysisOverride, DescriptionShape, ModelSchemaFact, PlainModel, PlainModelBlocker,
    PlainModelCheck,
};
use crate::compiled_project::tests::helpers::plain_check;
use crate::compiled_project::tests::test_types::{PlainBlockerTestCase, PlainFactsTestCase};

#[test]
fn given_model_check_when_classifying_then_only_plain_models_stay_native() {
    let test_cases = [
        PlainBlockerTestCase {
            description: "description and tags are plain",
            check: PlainModelCheck {
                description: DescriptionShape::Text("Orders.".to_owned()),
                ..plain_check("SELECT 1", &["description", "tags"])
            },
            expected_blocker: None,
        },
        PlainBlockerTestCase {
            description: "failed interpolation",
            check: PlainModelCheck {
                interpolated_sql: None,
                ..plain_check("", &[])
            },
            expected_blocker: Some(PlainModelBlocker::Interpolation),
        },
        PlainBlockerTestCase {
            description: "macro call",
            check: plain_check("SELECT @cents(amount)", &[]),
            expected_blocker: Some(PlainModelBlocker::Macros),
        },
        PlainBlockerTestCase {
            description: "hooks",
            check: plain_check("SELECT 1", &["post_hooks"]),
            expected_blocker: Some(PlainModelBlocker::CallbackConfig),
        },
        PlainBlockerTestCase {
            description: "declared columns",
            check: plain_check("SELECT 1", &["columns"]),
            expected_blocker: Some(PlainModelBlocker::HeaderMetadata),
        },
        PlainBlockerTestCase {
            description: "blank description",
            check: PlainModelCheck {
                description: DescriptionShape::Invalid,
                ..plain_check("SELECT 1", &["description"])
            },
            expected_blocker: Some(PlainModelBlocker::HeaderMetadata),
        },
        PlainBlockerTestCase {
            description: "analysis opted out",
            check: PlainModelCheck {
                analysis_override: AnalysisOverride::Disabled,
                ..plain_check("SELECT 1", &["sql_analysis"])
            },
            expected_blocker: Some(PlainModelBlocker::SqlAnalysisDisabled),
        },
        PlainBlockerTestCase {
            description: "enum or constant reference",
            check: PlainModelCheck {
                has_declaration_references: true,
                ..plain_check("SELECT 1", &[])
            },
            expected_blocker: Some(PlainModelBlocker::Declarations),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            plain_model_blocker(&test_case.check),
            test_case.expected_blocker,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_plain_model_when_finishing_then_description_attaches_empty_schema() {
    let test_cases = [
        PlainFactsTestCase {
            description: "described model",
            model_description: Some("Orders."),
            expected_schema: Some(ModelSchemaFact::default()),
        },
        PlainFactsTestCase {
            description: "undescribed model",
            model_description: None,
            expected_schema: None,
        },
    ];

    for test_case in test_cases {
        let facts = plain_model_facts(PlainModel {
            name: "orders".to_owned(),
            description: test_case.model_description.map(str::to_owned),
            ..PlainModel::default()
        });

        assert_eq!(
            facts.schema, test_case.expected_schema,
            "{}",
            test_case.description
        );
    }
}
