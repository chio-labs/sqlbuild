use crate::config_values::models::ConfigNode;
use crate::model_config_build::main::build_model_config::build_model_config;
use crate::model_config_build::models::{ConfigBuildInputs, ModelHeader};
use crate::model_config_build::tests::test_types::{BuildOutcome, BuildTestCase, FixedHost, Node};

/// A string node.
pub(super) fn text(value: &str) -> Node {
    ConfigNode::Str(value.to_owned())
}

/// A string-keyed entry.
pub(super) fn named(key: &str, value: Node) -> (Node, Node) {
    (text(key), value)
}

/// The values and reads of building `orders` from the case's header, or the error text.
pub(super) fn built(test_case: &BuildTestCase) -> BuildOutcome {
    let inputs: ConfigBuildInputs<u8> = ConfigBuildInputs {
        defaults: vec![
            named("materialized", text("view")),
            named("tags", ConfigNode::List(vec![text("core")])),
        ],
        path_defaults: Vec::new(),
        variables: vec![
            named("region", text("north")),
            named("count", ConfigNode::Int(3)),
        ],
        run_id: text("run_1"),
        target_name: text("dev"),
        target_namespace: test_case.target_namespace.clone(),
    };
    let host = FixedHost {
        environment: vec![("SCHEMA_SUFFIX", "eu")],
    };
    let header = ModelHeader {
        entries: &test_case.header,
        facts: None,
    };
    build_model_config((&host, &inputs), header, None, "orders")
        .map(|built| (built.values, built.reads))
}
