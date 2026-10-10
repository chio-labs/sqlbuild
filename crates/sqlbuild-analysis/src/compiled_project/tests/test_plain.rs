use crate::compiled_project::main::analysis_gate::analysis_gate;
use crate::compiled_project::models::{AnalysisGate, AnalysisOverride};
use crate::compiled_project::tests::helpers::analysing_settings;
use crate::compiled_project::tests::test_types::AnalysisGateTestCase;

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
