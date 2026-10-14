use crate::audit_command::main::audit_exit_code::audit_exit_code;
use crate::audit_command::main::render_audit_header::render_audit_header;
use crate::audit_command::main::render_audit_summary::render_audit_summary;
use crate::audit_command::models::AuditCounts;
use crate::audit_command::tests::test_types::{HeaderTestCase, SummaryTestCase};
use crate::cli_text::models::CliStyle;

const PLAIN: CliStyle = CliStyle { use_color: false };

#[test]
fn given_selected_audits_when_rendering_header_then_counts_audits_and_models() {
    let test_cases = [
        HeaderTestCase {
            description: "audits across models",
            counts: (28, 7),
            expected_text: "\nAudit (28 selected, 7 models)\n\n",
        },
        HeaderTestCase {
            description: "nothing selected",
            counts: (0, 0),
            expected_text: "\nAudit (0 selected, 0 models)\n\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_audit_header(test_case.counts, PLAIN),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_outcomes_when_summarizing_then_counts_and_fails_only_on_errors() {
    let test_cases = [
        SummaryTestCase {
            description: "a warning keeps a zero exit code",
            counts: AuditCounts {
                passed: 27,
                warned: 1,
                total: 28,
                ..AuditCounts::default()
            },
            expected_text: "\nPASS=27  WARN=1  FAIL=0  INSUFFICIENT=0  TOTAL=28\n",
            expected_exit_code: 0,
        },
        SummaryTestCase {
            description: "an error fails the run",
            counts: AuditCounts {
                passed: 26,
                failed: 1,
                insufficient: 1,
                total: 28,
                ..AuditCounts::default()
            },
            expected_text: "\nPASS=26  WARN=0  FAIL=1  INSUFFICIENT=1  TOTAL=28\n",
            expected_exit_code: 1,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_audit_summary(test_case.counts, PLAIN),
            test_case.expected_text,
            "{}",
            test_case.description
        );
        assert_eq!(
            audit_exit_code(test_case.counts.failed),
            test_case.expected_exit_code,
            "{}",
            test_case.description
        );
    }
}
