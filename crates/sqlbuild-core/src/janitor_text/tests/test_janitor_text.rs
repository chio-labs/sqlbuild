use crate::cli_text::models::CliStyle;
use crate::janitor_text::main::janitor_confirmation_prompt::janitor_confirmation_prompt;
use crate::janitor_text::main::janitor_disabled_text::janitor_disabled_text;
use crate::janitor_text::main::validate_janitor_settings::validate_janitor_settings;
use crate::janitor_text::models::JanitorPlanText;
use crate::janitor_text::tests::helpers::direct_archive_plan;
use crate::janitor_text::tests::test_types::{
    ConfirmationTestCase, DisabledTestCase, SettingsTestCase,
};

#[test]
fn given_plan_when_prompting_then_phrase_counts_every_action() {
    let test_cases = [
        ConfirmationTestCase {
            description: "a direct archive plan names archive and delete counts",
            plan: direct_archive_plan(),
            expected_prompt: "Janitor will archive 1 and delete 1 objects from dev.\n\
                Retention: 14 days\nArchive retention: 14 days\n\n\
                Type `archive 1 and delete 1 objects from dev` to continue: ",
        },
        ConfirmationTestCase {
            description: "state pruning counts items and zero retention skips age checks",
            plan: JanitorPlanText {
                target_name: None,
                retention_days: 0,
                state_prunes: vec![("main._sqlbuild_fingerprints".to_owned(), 2)],
                ..direct_archive_plan()
            },
            expected_prompt: "Janitor will archive 1 and delete 2 items from default.\n\
                Retention: disabled (0 days)\nAge metadata will not be checked.\n\
                Archive retention: 14 days\n\n\
                Type `archive 1 and delete 2 items from default` to continue: ",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            janitor_confirmation_prompt(&test_case.plan),
            test_case.expected_prompt,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_settings_when_validating_then_negative_values_fail() {
    let test_cases = [
        SettingsTestCase {
            description: "zero values are valid",
            retention_days: 0,
            history_versions: 0,
            expected_code: None,
        },
        SettingsTestCase {
            description: "negative retention fails first",
            retention_days: -1,
            history_versions: -1,
            expected_code: Some("C501"),
        },
        SettingsTestCase {
            description: "negative history fails",
            retention_days: 3,
            history_versions: -1,
            expected_code: Some("C502"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            validate_janitor_settings(test_case.retention_days, test_case.history_versions)
                .err()
                .map(|error| error.code),
            test_case.expected_code,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_disabled_janitor_when_rendering_then_guidance_matches() {
    let test_cases = [DisabledTestCase {
        description: "preserves disabled no-color output",
        use_color: false,
        expected_text: "Janitor is disabled for this project.\n\n\
         Janitor is opt-in. It previews stale warehouse objects and asks before archiving or \
         deleting anything.\n\nAdd this block to sqlbuild_project.toml:\n\n[janitor]\n\
         enabled = true\n\nAfter enabling, run janitor again to preview cleanup:\n  sqb janitor\n",
    }];

    for test_case in test_cases {
        assert_eq!(
            janitor_disabled_text(CliStyle {
                use_color: test_case.use_color
            }),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
