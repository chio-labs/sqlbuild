use crate::dbt_cli::main::dbt_flag_value::dbt_flag_value;
use crate::dbt_cli::tests::test_types::FlagValueTestCase;

#[test]
fn given_routed_dbt_args_when_reading_a_flag_then_returns_the_first_value() {
    let test_cases = [
        FlagValueTestCase {
            description: "the value after the first occurrence",
            args: &["--target", "dev", "--target", "prod"],
            flag: "--target",
            expected_value: Some("dev"),
        },
        FlagValueTestCase {
            description: "a trailing flag has no value",
            args: &["--select", "a", "--target"],
            flag: "--target",
            expected_value: None,
        },
        FlagValueTestCase {
            description: "only exact flags match",
            args: &["--target=dev"],
            flag: "--target",
            expected_value: None,
        },
    ];

    for test_case in test_cases {
        let args: Vec<String> = test_case.args.iter().map(|arg| (*arg).to_owned()).collect();
        assert_eq!(
            dbt_flag_value(&args, test_case.flag).as_deref(),
            test_case.expected_value,
            "{}",
            test_case.description
        );
    }
}
