use crate::key_checks::main::unknown_mapping_keys::unknown_mapping_keys;
use crate::key_checks::tests::test_types::UnknownKeysTestCase;

#[test]
fn given_mapping_keys_when_checking_then_unknown_keys_are_sorted_with_a_suggestion() {
    let test_cases = [
        UnknownKeysTestCase {
            description: "allowed keys pass",
            keys: vec![("name".to_owned(), true)],
            expected_failure: None,
        },
        UnknownKeysTestCase {
            description: "a misspelt key is suggested",
            keys: vec![("nme".to_owned(), true), ("name".to_owned(), true)],
            expected_failure: Some((
                "has unknown keys: nme; allowed keys: columns, name",
                "did you mean 'name'?",
            )),
        },
        UnknownKeysTestCase {
            description: "a non-string key is never allowed",
            keys: vec![("name".to_owned(), false)],
            expected_failure: Some((
                "has unknown keys: name; allowed keys: columns, name",
                "did you mean 'name'?",
            )),
        },
    ];
    let allowed = ["name".to_owned(), "columns".to_owned()];

    for test_case in test_cases {
        let failure = unknown_mapping_keys(&test_case.keys, &allowed);

        assert_eq!(
            failure,
            test_case
                .expected_failure
                .map(|(message, help)| (message.to_owned(), help.to_owned())),
            "{}",
            test_case.description
        );
    }
}
