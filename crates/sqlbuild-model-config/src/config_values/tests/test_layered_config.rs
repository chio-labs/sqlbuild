use crate::config_values::main::layered_config::layered_config;
use crate::config_values::models::ConfigNode;
use crate::config_values::tests::helpers::{text, texts};
use crate::config_values::tests::test_types::{LayeredConfigTestCase, Node};

#[test]
fn given_two_layers_when_merged_then_overrides_keep_order_and_unions_merge() {
    let test_cases = [
        LayeredConfigTestCase {
            description: "an override keeps the key's place; a new key is appended",
            base: vec![
                (text("materialized"), text("view")),
                (text("schema"), text("raw")),
            ],
            overlay: vec![
                (text("alias"), text("orders")),
                (text("materialized"), text("table")),
            ],
            expected_entries: vec![
                (text("materialized"), text("table")),
                (text("schema"), text("raw")),
                (text("alias"), text("orders")),
            ],
            expected_unioned_keys: vec![],
        },
        LayeredConfigTestCase {
            description: "tags and row-diff exclusions union as list and tuple",
            base: vec![
                (text("tags"), texts(&["daily", "core"])),
                (
                    text("row_diff_exclude_columns"),
                    ConfigNode::Tuple(vec![text("updated_at")]),
                ),
            ],
            overlay: vec![
                (text("tags"), texts(&["core", "finance"])),
                (text("row_diff_exclude_columns"), texts(&["loaded_at"])),
            ],
            expected_entries: vec![
                (text("tags"), texts(&["daily", "core", "finance"])),
                (
                    text("row_diff_exclude_columns"),
                    ConfigNode::Tuple(vec![text("updated_at"), text("loaded_at")]),
                ),
            ],
            expected_unioned_keys: vec!["tags", "row_diff_exclude_columns"],
        },
        LayeredConfigTestCase {
            description: "a null overlay tag list overrides without a union",
            base: vec![(text("tags"), texts(&["daily"]))],
            overlay: vec![(text("tags"), ConfigNode::Null)],
            expected_entries: vec![(text("tags"), ConfigNode::Null)],
            expected_unioned_keys: vec![],
        },
        LayeredConfigTestCase {
            description: "tolerance sections merge one level deeper",
            base: vec![(
                text("row_diff_tolerances"),
                ConfigNode::Map(vec![
                    (
                        text("by_type"),
                        ConfigNode::Map(vec![(text("float"), ConfigNode::Float(0.1))]),
                    ),
                    (text("default"), ConfigNode::Int(0)),
                ]),
            )],
            overlay: vec![(
                text("row_diff_tolerances"),
                ConfigNode::Map(vec![
                    (
                        text("by_type"),
                        ConfigNode::Map(vec![(text("decimal"), ConfigNode::Int(1))]),
                    ),
                    (text("default"), ConfigNode::Int(2)),
                ]),
            )],
            expected_entries: vec![(
                text("row_diff_tolerances"),
                ConfigNode::Map(vec![
                    (
                        text("by_type"),
                        ConfigNode::Map(vec![
                            (text("float"), ConfigNode::Float(0.1)),
                            (text("decimal"), ConfigNode::Int(1)),
                        ]),
                    ),
                    (text("default"), ConfigNode::Int(2)),
                ]),
            )],
            expected_unioned_keys: vec!["row_diff_tolerances"],
        },
    ];
    for test_case in test_cases {
        let text = |_: &Node| -> Result<String, ()> { Err(()) };
        let layered = layered_config(&test_case.base, &test_case.overlay, &text)
            .expect("plain scalar unions need no host text");
        assert_eq!(
            (layered.entries, layered.unioned_keys),
            (test_case.expected_entries, test_case.expected_unioned_keys),
            "{}",
            test_case.description
        );
    }
}
