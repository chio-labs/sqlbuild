use crate::project::main::explicit_references_help::explicit_references_help;
use crate::project::main::microbatch_guidance::microbatch_guidance;
use crate::project::main::sql_analysis_off_guidance::sql_analysis_off_guidance;
use crate::project::tests::test_types::GuidanceTestCase;

#[test]
fn given_setting_guidance_when_rendering_then_text_matches_python() {
    let test_cases = [
        GuidanceTestCase {
            description: "microbatch concurrency",
            rendered: microbatch_guidance(),
            expected_note: "the current value is [settings] microbatch_concurrency = false (from sqlbuild_project.toml or its default)",
            expected_help: "to run microbatches concurrently, set this in sqlbuild_project.toml:\n            [settings]\n            microbatch_concurrency = true",
        },
        GuidanceTestCase {
            description: "SQL analysis turned off locally",
            rendered: sql_analysis_off_guidance(true, "to run X"),
            expected_note: "sqlbuild_local.toml sets [settings] sql_analysis = false",
            expected_help: "to run X, set this in sqlbuild_local.toml:\n            [settings]\n            sql_analysis = true",
        },
        GuidanceTestCase {
            description: "explicit references",
            rendered: (explicit_references_help("X"), String::new()),
            expected_note: "the current value is [references] enforce_explicit = true (from sqlbuild_project.toml or its default); while migrating a project, to allow X, set this in sqlbuild_project.toml:\n            [references]\n            enforce_explicit = false",
            expected_help: "",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (test_case.rendered.0.as_str(), test_case.rendered.1.as_str()),
            (test_case.expected_note, test_case.expected_help),
            "{}",
            test_case.description
        );
    }
}
