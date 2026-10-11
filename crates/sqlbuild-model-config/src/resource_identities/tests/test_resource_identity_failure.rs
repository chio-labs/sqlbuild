use crate::resource_identities::main::resource_identity_failure::resource_identity_failure;
use crate::resource_identities::tests::test_types::ResourceIdentityTestCase;

#[test]
fn given_identities_when_validating_then_only_snake_case_passes_with_python_suggestions() {
    let test_cases = [
        ResourceIdentityTestCase {
            description: "canonical public identity",
            name: "orders__daily2",
            private_identity: false,
            expected_suggestion: None,
        },
        ResourceIdentityTestCase {
            description: "acronym and word boundaries",
            name: " HTTPStatusCode ",
            private_identity: false,
            expected_suggestion: Some("http_status_code"),
        },
        ResourceIdentityTestCase {
            description: "invalid runs collapse and edges trim",
            name: "-Orders--éx_",
            private_identity: false,
            expected_suggestion: Some("orders_x"),
        },
        ResourceIdentityTestCase {
            description: "private identities keep their underscore",
            name: "_customer_ids",
            private_identity: true,
            expected_suggestion: None,
        },
        ResourceIdentityTestCase {
            description: "a private identity is suggested with its underscore",
            name: "CustomerIds",
            private_identity: true,
            expected_suggestion: Some("_customer_ids"),
        },
        ResourceIdentityTestCase {
            description: "nothing valid falls back",
            name: "***",
            private_identity: false,
            expected_suggestion: Some("resource_name"),
        },
    ];

    for test_case in test_cases {
        let failure = resource_identity_failure(test_case.name, test_case.private_identity);

        assert_eq!(
            failure.map(|(suggestion, _)| suggestion),
            test_case.expected_suggestion.map(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
