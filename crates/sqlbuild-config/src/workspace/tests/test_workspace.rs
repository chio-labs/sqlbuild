use sqlbuild_core::cli_text::models::CliStyle;

use crate::workspace::_helpers::skill_files::with_marker;
use crate::workspace::main::playground_summary::playground_summary;
use crate::workspace::tests::test_types::{MarkerTestCase, SummaryTestCase};

#[test]
fn given_skill_content_when_marking_then_marker_follows_frontmatter() {
    let test_cases = [
        MarkerTestCase {
            description: "the marker follows frontmatter",
            content: "---\nname: sqlbuild\n---\n# SQLBuild Skill\n",
            expected_content: "---\nname: sqlbuild\n---\n\n<!-- generated-by: sqlbuild skills -->\n# SQLBuild Skill\n",
        },
        MarkerTestCase {
            description: "the legacy marker is replaced",
            content: "<!-- generated-by: sqlbuild skills update -->\nbody\n",
            expected_content: "<!-- generated-by: sqlbuild skills -->\nbody\n",
        },
        MarkerTestCase {
            description: "content without frontmatter starts with the marker",
            content: "body\n",
            expected_content: "<!-- generated-by: sqlbuild skills -->\nbody\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            with_marker(test_case.content.to_owned()),
            test_case.expected_content,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_playground_template_when_summarizing_then_next_steps_match_the_template() {
    let test_cases = [SummaryTestCase {
        description: "an orchestrated template enters and leaves the nested project",
        template: "dagster",
        expected_text: "SQLBuild playground created\n\n  Project: demo\n  Adapter: DuckDB\n  Example: waffle shop + Dagster\n\nTry:\n  cd demo/waffle_shop\n  sqb compile\n  sqb build\n  sqb test\n  sqb audit\n  cd ..\n  DAGSTER_IS_DEV_CLI=1 dagster dev -f definitions.py\n",
    }];

    for test_case in test_cases {
        assert_eq!(
            playground_summary("demo", test_case.template, CliStyle { use_color: false }),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
