use crate::lineage_graph::main::analysis_dialect::analysis_dialect;
use crate::lineage_graph::main::edge_index::edge_index;
use crate::lineage_graph::main::tree_lines::tree_lines;
use crate::lineage_graph::models::{AnalysisDialect, EdgeIndex, EdgeKey};
use crate::lineage_graph::tests::helpers::edge_key;
use crate::lineage_graph::tests::test_types::{
    AnalysisDialectTestCase, EdgeIndexTestCase, StringTree, TreeLinesTestCase,
};

#[test]
fn given_edges_when_indexing_then_positions_keep_edge_order_and_equal_edges_share_one() {
    let test_cases = [EdgeIndexTestCase {
        description: "repeated and interleaved edges",
        edges: &[
            (("orders", "id"), ("customers", "order_id")),
            (("products", "id"), ("orders", "product_id")),
            (("orders", "id"), ("customers", "order_id")),
            (("orders", "total"), ("customers", "spend")),
        ],
        expected_targeting_orders: &[0, 2, 3],
        expected_sourced_from_orders: &[0, 2, 3],
        expected_first_equal: &[0, 1, 0, 3],
    }];
    for test_case in test_cases {
        let edges: Vec<EdgeKey> = test_case
            .edges
            .iter()
            .map(|(source, target)| edge_key(*source, *target))
            .collect();
        let index: EdgeIndex = edge_index(&edges);
        assert_eq!(
            index.by_target_model.get("customers").map(Vec::as_slice),
            Some(test_case.expected_targeting_orders),
            "{}",
            test_case.description
        );
        assert_eq!(
            index.by_source_resource.get("orders").map(Vec::as_slice),
            Some(test_case.expected_sourced_from_orders),
            "{}",
            test_case.description
        );
        assert_eq!(
            index.first_equal.as_slice(),
            test_case.expected_first_equal,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_dialect_names_when_resolving_then_aliases_map_and_others_stay_named() {
    let test_cases = [
        AnalysisDialectTestCase {
            description: "an empty name is generic",
            normalized: "",
            expected_dialect: AnalysisDialect::Alias("generic"),
        },
        AnalysisDialectTestCase {
            description: "MotherDuck analyzes as DuckDB",
            normalized: "motherduck",
            expected_dialect: AnalysisDialect::Alias("duckdb"),
        },
        AnalysisDialectTestCase {
            description: "SQL Server analyzes as T-SQL",
            normalized: "sqlserver",
            expected_dialect: AnalysisDialect::Alias("tsql"),
        },
        AnalysisDialectTestCase {
            description: "other names are looked up as given",
            normalized: "mysql",
            expected_dialect: AnalysisDialect::Named("mysql"),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            analysis_dialect(test_case.normalized),
            test_case.expected_dialect,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_graph_when_drawing_a_tree_then_each_node_expands_once() {
    let test_cases = [TreeLinesTestCase {
        description: "a diamond expands its shared node once and skips the focus",
        children: &[
            ("orders", &["customers", "products"]),
            ("customers", &["regions", "orders"]),
            ("products", &["regions"]),
            ("regions", &["countries"]),
        ],
        roots: &["customers", "products"],
        seen: &["orders"],
        expected_lines: &[
            "├── customers",
            "│   ├── regions",
            "│   │   └── countries",
            "│   └── orders (shown)",
            "└── products",
            "    └── regions (shown)",
        ],
    }];
    for test_case in test_cases {
        let mut tree = StringTree {
            children: test_case
                .children
                .iter()
                .map(|(node, children)| (*node, children.to_vec()))
                .collect(),
            lines: Vec::new(),
        };
        let Ok(()) = tree_lines(
            test_case.roots.to_vec(),
            test_case.seen.iter().copied().collect(),
            &mut tree,
        );
        assert_eq!(
            tree.lines, test_case.expected_lines,
            "{}",
            test_case.description
        );
    }
}
