use crate::contracts::main::promotion_conflicts::promotion_conflicts;
use crate::contracts::models::{PromotionConflict, PromotionRequest};
use crate::contracts::tests::helpers::promotion_model;
use crate::contracts::tests::test_types::PromotionTestCase;

const ADAPTER_DEFAULT_HELP: &str = "sqlbuild_project.toml does not set [settings] \
    table_promotion_mode, so it defaults to \"immediate\"; enforced contracts are validated in a \
    staging table before promotion\n  = help: to validate enforced contracts before promotion, \
    set this in sqlbuild_project.toml:\n            [settings]\n            \
    table_promotion_mode = \"staged\"\n  = help: or remove the model's enforced contract: \
    `contract enforced` in its MODEL header, or `contract = \"enforced\"` in the [defaults] or \
    [path_defaults] entry that applies to it";
const EXPLICIT_OVER_STAGED_HELP: &str = "sqlbuild_local.toml sets [settings] \
    table_promotion_mode = \"immediate\"; enforced contracts are validated in a staging table \
    before promotion\n  = help: remove that line to use the default staged promotion, or set \
    this in sqlbuild_local.toml:\n            [settings]\n            \
    table_promotion_mode = \"staged\"\n  = help: or remove the model's enforced contract: \
    `contract enforced` in its MODEL header, or `contract = \"enforced\"` in the [defaults] or \
    [path_defaults] entry that applies to it";

fn request(
    explicit_mode: Option<&str>,
    adapter_default: &str,
    settings_file: &str,
) -> PromotionRequest {
    PromotionRequest {
        explicit_mode: explicit_mode.map(str::to_owned),
        adapter_default: adapter_default.to_owned(),
        settings_file: settings_file.to_owned(),
        models: vec![
            promotion_model(Some("enforced"), Some("table"), None),
            promotion_model(Some("enforced"), Some("view"), None),
            promotion_model(Some("enforced"), Some("incremental"), Some("microbatch")),
            promotion_model(None, Some("table"), None),
            promotion_model(Some("enforced"), Some("incremental"), Some("merge")),
            promotion_model(Some("enforced"), None, None),
        ],
    }
}

#[test]
fn given_promotion_settings_when_checking_conflicts_then_only_immediate_staged_lifecycles_conflict()
{
    let test_cases = [
        PromotionTestCase {
            description: "staged by default",
            request: request(None, "staged", "sqlbuild_project.toml"),
            expected_models: &[],
            expected_help: None,
        },
        PromotionTestCase {
            description: "immediate by adapter default",
            request: request(None, "immediate", "sqlbuild_project.toml"),
            expected_models: &[0, 4],
            expected_help: Some(ADAPTER_DEFAULT_HELP),
        },
        PromotionTestCase {
            description: "explicit immediate over a staged adapter default",
            request: request(Some("immediate"), "staged", "sqlbuild_local.toml"),
            expected_models: &[0, 4],
            expected_help: Some(EXPLICIT_OVER_STAGED_HELP),
        },
        PromotionTestCase {
            description: "explicit staged over an immediate adapter default",
            request: request(Some("staged"), "immediate", "sqlbuild_project.toml"),
            expected_models: &[],
            expected_help: None,
        },
    ];
    for test_case in test_cases {
        let conflicts: Vec<PromotionConflict> = promotion_conflicts(&test_case.request);
        assert_eq!(
            conflicts
                .iter()
                .map(|conflict| conflict.model_index)
                .collect::<Vec<_>>(),
            test_case.expected_models,
            "{}",
            test_case.description
        );
        assert_eq!(
            conflicts.first().map(|conflict| conflict.help.as_str()),
            test_case.expected_help,
            "{}",
            test_case.description
        );
    }
}
