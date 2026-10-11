use crate::audits::main::resolve_audit_policies::resolve_audit_policies;
use crate::audits::tests::test_types::AuditPoliciesTestCase;

#[test]
fn given_audit_policies_when_resolving_then_instance_then_project_then_fallback_wins() {
    let test_cases = [
        AuditPoliciesTestCase {
            description: "nothing authored falls back",
            severity: (None, None),
            run_scope: (None, None),
            expected_policies: Ok(("error", "delta_and_final")),
        },
        AuditPoliciesTestCase {
            description: "instance values override project defaults",
            severity: (Some("warn"), Some("error")),
            run_scope: (Some("final"), Some("delta_and_final")),
            expected_policies: Ok(("warn", "final")),
        },
        AuditPoliciesTestCase {
            description: "project defaults apply without instance values",
            severity: (None, Some("warn")),
            run_scope: (None, Some("final")),
            expected_policies: Ok(("warn", "final")),
        },
        AuditPoliciesTestCase {
            description: "an unknown instance run scope is rejected",
            severity: (None, None),
            run_scope: (Some("always"), None),
            expected_policies: Err(
                "unknown audit run_scope 'always'; valid values: delta_and_final, final",
            ),
        },
    ];

    for test_case in test_cases {
        let (instance, default) = test_case.severity;
        assert_eq!(
            resolve_audit_policies((instance, default, "audit 'floor'"), test_case.run_scope)
                .as_ref()
                .map(|(severity, run_scope)| (*severity, run_scope.as_str()))
                .map_err(String::as_str),
            test_case.expected_policies,
            "{}",
            test_case.description
        );
    }
}
