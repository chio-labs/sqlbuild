use crate::audits::models::ArgumentValue;
use crate::audits::tests::helpers::{attachment, rendering_text};
use crate::audits::tests::test_types::AttachedAuditTestCase;

#[test]
fn given_attached_audits_when_rendering_then_python_rendering_is_returned() {
    let values: (String, ArgumentValue) = (
        "values".to_owned(),
        ArgumentValue::List(vec![ArgumentValue::Number("1".to_owned())]),
    );
    let test_cases = [
        AttachedAuditTestCase {
            description: "explicit arguments merge after implicit ones with default policies",
            attachment: attachment(vec![values.clone()], None, None),
            expected_rendering: Some(
                "SELECT * FROM t WHERE status NOT IN (1) | SELECT status FROM t | error | Fallback",
            ),
        },
        AttachedAuditTestCase {
            description: "instance severity and run scope",
            attachment: attachment(vec![values.clone()], Some("warn"), Some("final")),
            expected_rendering: Some(
                "SELECT * FROM t WHERE status NOT IN (1) | SELECT status FROM t | warn | Instance",
            ),
        },
        AttachedAuditTestCase {
            description: "an explicit argument overriding an implicit one defers",
            attachment: attachment(
                vec![(
                    "column".to_owned(),
                    ArgumentValue::Text("amount".to_owned()),
                )],
                None,
                None,
            ),
            expected_rendering: None,
        },
        AttachedAuditTestCase {
            description: "an unknown severity defers so Python raises",
            attachment: attachment(vec![values.clone()], Some("fatal"), None),
            expected_rendering: None,
        },
        AttachedAuditTestCase {
            description: "an unknown run scope defers so Python raises",
            attachment: attachment(vec![values], None, Some("delta")),
            expected_rendering: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            rendering_text(&test_case.attachment).as_deref(),
            test_case.expected_rendering,
            "{}",
            test_case.description
        );
    }
}
