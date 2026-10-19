use crate::dispatch::main::invocation_policy::invocation_policy;
use crate::dispatch::models::{CommandFacts, InvocationPolicy};
use crate::dispatch::tests::helpers::facts;
use crate::dispatch::tests::test_types::InvocationPolicyTestCase;

#[test]
fn given_parsed_command_when_choosing_services_then_matches_python_entry_rules() {
    let test_cases = [
        InvocationPolicyTestCase {
            description: "compile is observed and checks skills",
            facts: facts("compile", None),
            expected_policy: InvocationPolicy {
                creates_project: false,
                observed: true,
                maintains_skills: true,
                recalled: true,
            },
        },
        InvocationPolicyTestCase {
            description: "dbt init creates a project",
            facts: facts("dbt", Some("init")),
            expected_policy: InvocationPolicy {
                creates_project: true,
                observed: false,
                maintains_skills: true,
                recalled: false,
            },
        },
        InvocationPolicyTestCase {
            description: "playground creates a project and skips skills",
            facts: facts("playground", None),
            expected_policy: InvocationPolicy {
                creates_project: true,
                observed: false,
                maintains_skills: false,
                recalled: false,
            },
        },
        InvocationPolicyTestCase {
            description: "a raw query diff is not observed, so it is not recorded either",
            facts: CommandFacts {
                raw_query_diff: true,
                ..facts("diff", None)
            },
            expected_policy: InvocationPolicy {
                creates_project: false,
                observed: false,
                maintains_skills: false,
                recalled: false,
            },
        },
        InvocationPolicyTestCase {
            description: "recall reads history and is never recorded itself",
            facts: facts("recall", Some("query")),
            expected_policy: InvocationPolicy {
                creates_project: false,
                observed: true,
                maintains_skills: true,
                recalled: false,
            },
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            invocation_policy(&test_case.facts),
            test_case.expected_policy,
            "{}",
            test_case.description
        );
    }
}
