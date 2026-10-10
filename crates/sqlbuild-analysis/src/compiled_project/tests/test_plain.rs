use crate::compiled_project::main::analysis_gate::analysis_gate;
use crate::compiled_project::main::enum_typed_columns::enum_typed_columns;
use crate::compiled_project::main::header_attachment_feature::header_attachment_feature;
use crate::compiled_project::models::{AnalysisGate, AnalysisOverride, AttachmentFeature};
use crate::compiled_project::tests::helpers::{analysing_settings, column, keys};
use crate::compiled_project::tests::test_types::{
    AnalysisGateTestCase, EnumColumnsTestCase, HeaderFeatureTestCase,
};

#[test]
fn given_override_when_gating_analysis_then_project_switches_come_first() {
    let test_cases = [
        AnalysisGateTestCase {
            description: "inherited",
            sql_analysis: true,
            analysis_override: AnalysisOverride::Inherit,
            expected_gate: AnalysisGate::Enabled,
        },
        AnalysisGateTestCase {
            description: "opted out",
            sql_analysis: true,
            analysis_override: AnalysisOverride::Disabled,
            expected_gate: AnalysisGate::Disabled,
        },
        AnalysisGateTestCase {
            description: "conflicting keys",
            sql_analysis: true,
            analysis_override: AnalysisOverride::Conflict,
            expected_gate: AnalysisGate::Conflict,
        },
        AnalysisGateTestCase {
            description: "project disables analysis before the conflict is read",
            sql_analysis: false,
            analysis_override: AnalysisOverride::Conflict,
            expected_gate: AnalysisGate::Disabled,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            analysis_gate(
                analysing_settings(test_case.sql_analysis),
                test_case.analysis_override
            ),
            test_case.expected_gate,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_header_keys_when_classifying_then_attachment_features_are_found_in_order() {
    let test_cases = [
        HeaderFeatureTestCase {
            description: "columns, audits, enums and constants are native",
            keys: &[
                "description",
                "columns",
                "audits",
                "enums",
                "constants",
                "pre_hooks",
            ],
            expected_feature: None,
        },
        HeaderFeatureTestCase {
            description: "model schema before dynamic columns",
            keys: &["dynamic_columns", "model_schema"],
            expected_feature: Some(AttachmentFeature::ModelSchema),
        },
        HeaderFeatureTestCase {
            description: "audit factories",
            keys: &["audit_factories"],
            expected_feature: Some(AttachmentFeature::AuditFactories),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            header_attachment_feature(&keys(test_case.keys)),
            test_case.expected_feature,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_header_columns_when_checking_enum_types_then_visible_enums_are_matched() {
    let test_cases = [
        EnumColumnsTestCase {
            description: "scalar column",
            column_type: Some("INTEGER"),
            expected_enum_typed: false,
        },
        EnumColumnsTestCase {
            description: "enum column",
            column_type: Some("order_status"),
            expected_enum_typed: true,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            enum_typed_columns(&[column(test_case.column_type)], &keys(&["order_status"])),
            test_case.expected_enum_typed,
            "{}",
            test_case.description
        );
    }
}
