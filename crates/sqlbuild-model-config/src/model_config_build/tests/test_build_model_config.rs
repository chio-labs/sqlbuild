use crate::config_values::models::ConfigNode;
use crate::errors::ConfigError;
use crate::model_config_build::models::ConfigBuildHalt;
use crate::model_config_build::tests::helpers::{built, named, text};
use crate::model_config_build::tests::test_types::BuildTestCase;

#[test]
fn given_model_headers_when_building_config_then_values_expand_and_layer_as_python_does() {
    let test_cases = [
        BuildTestCase {
            description: "the header overrides defaults and tags union in place",
            header: vec![
                named("tags", ConfigNode::List(vec![text("orders")])),
                named("materialized", text("table")),
            ],
            target_namespace: None,
            expected_outcome: Ok((
                vec![
                    named("materialized", text("table")),
                    named("tags", ConfigNode::List(vec![text("core"), text("orders")])),
                ],
                vec![],
            )),
        },
        BuildTestCase {
            description: "templates read variables, the environment and the model context",
            header: vec![named(
                "alias",
                text("${CTX:model.name}_${region}_${ENV:SCHEMA_SUFFIX}_${count}"),
            )],
            target_namespace: None,
            expected_outcome: Ok((
                vec![
                    named("materialized", text("view")),
                    named("tags", ConfigNode::List(vec![text("core")])),
                    named("alias", text("orders_north_eu_3")),
                ],
                vec![
                    ("ctx", "model.name".to_owned()),
                    ("env", "SCHEMA_SUFFIX".to_owned()),
                    ("ctx", "model.name".to_owned()),
                ],
            )),
        },
        BuildTestCase {
            description: "the target schema expands with the model context",
            header: vec![],
            target_namespace: Some((ConfigNode::Null, text("${region}_${CTX:model.name}"))),
            expected_outcome: Ok((
                vec![
                    named("materialized", text("view")),
                    named("tags", ConfigNode::List(vec![text("core")])),
                    named("schema", text("north_orders")),
                ],
                vec![("ctx", "model.name".to_owned())],
            )),
        },
        BuildTestCase {
            description: "a preserved target schema needs a logical schema",
            header: vec![],
            target_namespace: Some((ConfigNode::Null, text("preserve"))),
            expected_outcome: Err(ConfigBuildHalt::Config(
                ConfigError::compile(
                    "Model 'orders' has no logical schema, but the selected target sets schema \
                     to 'preserve'"
                        .to_owned(),
                )
                .with_help(
                    "Set schema on the resource or its defaults, or configure a literal target \
                     schema.",
                ),
            )),
        },
        BuildTestCase {
            description: "a macro call in a config value is rejected",
            header: vec![named("description", text("@py.note()"))],
            target_namespace: None,
            expected_outcome: Err(ConfigBuildHalt::Config(ConfigError::compile(
                "model config field 'description' does not allow macros".to_owned(),
            ))),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            built(&test_case),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}
