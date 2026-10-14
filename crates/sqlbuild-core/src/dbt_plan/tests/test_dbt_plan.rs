use crate::dbt_cli::models::{DbtCliOptionValues, DbtInteropCommandKind};
use crate::dbt_plan::main::dbt_failure_detail::dbt_failure_detail;
use crate::dbt_plan::main::dbt_plan_argvs::dbt_plan_argvs;
use crate::dbt_plan::main::dbt_required_selector_terms::dbt_required_selector_terms;
use crate::dbt_plan::models::{DbtPlanArgvRequest, DbtReferencedModel};
use crate::dbt_plan::tests::helpers::{flattened, texts};
use crate::dbt_plan::tests::test_types::{ArgvsTestCase, TextsTestCase};

#[test]
fn given_plan_inputs_when_building_argvs_then_maps_commands() {
    let options: DbtCliOptionValues = DbtCliOptionValues {
        target: Some("prod".to_owned()),
        defer: true,
        ..DbtCliOptionValues::default()
    };
    let (dbt_args, sqlbuild_args, models, terms) = (
        texts(&["--select", "a+"]),
        texts(&["--vars", "{}"]),
        texts(&["fact", "mart"]),
        texts(&["+fqn:a.stg"]),
    );
    let request = |command: DbtInteropCommandKind, models: &'static [String]| DbtPlanArgvRequest {
        command,
        dbt_executable: "dbt",
        sqlbuild_executable: "sqb",
        options: &options,
        dbt_command_args: &dbt_args,
        sqlbuild_command_args: &sqlbuild_args,
        selected_model_names: models,
        required_selector_terms: &terms,
    };
    let test_cases = [
        ArgvsTestCase {
            description: "plan lists with dbt ls and plans SQLBuild",
            argvs: flattened(dbt_plan_argvs(&DbtPlanArgvRequest {
                selected_model_names: &models,
                ..request(DbtInteropCommandKind::Plan, &[])
            })),
            expected_argvs: vec![
                vec!["dbt", "ls", "--select", "a+"],
                vec!["sqb", "plan", "--select", "fact", "mart", "--vars", "{}"],
                vec![
                    "dbt",
                    "ls",
                    "--target",
                    "prod",
                    "--defer",
                    "--select",
                    "+fqn:a.stg",
                ],
            ],
        },
        ArgvsTestCase {
            description: "run builds SQLBuild models without tests",
            argvs: flattened(dbt_plan_argvs(&DbtPlanArgvRequest {
                selected_model_names: &models,
                required_selector_terms: &[],
                ..request(DbtInteropCommandKind::Run, &[])
            })),
            expected_argvs: vec![
                vec!["dbt", "run", "--select", "a+"],
                vec![
                    "sqb",
                    "build",
                    "--no-tests",
                    "--no-audits",
                    "--select",
                    "fact",
                    "mart",
                    "--vars",
                    "{}",
                ],
            ],
        },
        ArgvsTestCase {
            description: "no selected models means no SQLBuild command",
            argvs: flattened(dbt_plan_argvs(&request(DbtInteropCommandKind::Build, &[]))),
            expected_argvs: vec![
                vec!["dbt", "build", "--select", "a+"],
                vec![
                    "dbt",
                    "build",
                    "--target",
                    "prod",
                    "--defer",
                    "--select",
                    "+fqn:a.stg",
                ],
            ],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            test_case.argvs, test_case.expected_argvs,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_dbt_outputs_when_summarising_then_returns_terms_and_details() {
    let referenced: Vec<DbtReferencedModel> = vec![
        DbtReferencedModel {
            unique_id: "model.a.stg".to_owned(),
            fqn: texts(&["a", "stg"]),
            name: "stg".to_owned(),
        },
        DbtReferencedModel {
            unique_id: "model.a.int".to_owned(),
            fqn: Vec::new(),
            name: "int".to_owned(),
        },
        DbtReferencedModel {
            unique_id: "model.a.stg".to_owned(),
            fqn: texts(&["a", "stg"]),
            name: "stg".to_owned(),
        },
    ];
    let test_cases = [
        TextsTestCase {
            description: "required terms are distinct and sorted",
            texts: dbt_required_selector_terms(
                &referenced,
                &texts(&["model.a.stg", "model.a.int"]),
            )
            .into_iter()
            .map(Some)
            .collect(),
            expected_texts: vec![Some("+fqn:a.stg"), Some("+int")],
        },
        TextsTestCase {
            description: "failure detail prefers stderr and drops blanks",
            texts: vec![
                dbt_failure_detail(" boom \n", "out"),
                dbt_failure_detail("", " out "),
                dbt_failure_detail("", " \n"),
            ],
            expected_texts: vec![Some("boom"), Some("out"), None],
        },
    ];

    for test_case in test_cases {
        let texts: Vec<Option<&str>> = test_case.texts.iter().map(Option::as_deref).collect();
        assert_eq!(texts, test_case.expected_texts, "{}", test_case.description);
    }
}
