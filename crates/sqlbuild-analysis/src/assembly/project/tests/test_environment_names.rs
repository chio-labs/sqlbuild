use crate::assembly::project::main::environment_template_names::environment_template_names;
use crate::assembly::project::tests::test_types::EnvironmentNamesTestCase;

#[test]
fn given_template_values_when_scanning_then_environment_names_match_python_findall() {
    let test_cases = [
        EnvironmentNamesTestCase {
            description: "names end at whitespace and template punctuation, deduplicated",
            values: &[
                Some("${ENV:WAREHOUSE}_db"),
                None,
                Some("ENV:a ENV:b,ENV:WAREHOUSE"),
            ],
            expected_names: &["WAREHOUSE", "a", "b"],
        },
        EnvironmentNamesTestCase {
            description: "an empty name is skipped and a nested prefix is part of the name",
            values: &[Some("ENV:)ENV:ENV:x\u{3000}y")],
            expected_names: &["ENV:x"],
        },
    ];

    for test_case in test_cases {
        let values: Vec<Option<String>> = test_case
            .values
            .iter()
            .map(|value| value.map(str::to_owned))
            .collect();

        let names = environment_template_names(&values);

        assert_eq!(
            names,
            test_case.expected_names.to_vec(),
            "{}",
            test_case.description
        );
    }
}
