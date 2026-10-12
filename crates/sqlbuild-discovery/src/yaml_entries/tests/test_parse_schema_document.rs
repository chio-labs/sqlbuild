use crate::yaml_entries::main::parse_schema_document::parse_schema_document;
use crate::yaml_entries::tests::test_types::{Node, map, text};

const PATH: &str = "/project/seeds/countries.yml";

fn seed(columns: Vec<Node>, extra: Vec<(&str, Node)>) -> Node {
    let mut entries: Vec<(&str, Node)> = vec![
        ("name", text("countries")),
        ("columns", Node::List(columns)),
    ];
    entries.extend(extra);
    map(vec![("seeds", Node::List(vec![map(entries)]))])
}

fn column(name: &str, column_type: Option<&str>) -> Node {
    let mut entries: Vec<(&str, Node)> = vec![("name", text(name))];
    if let Some(column_type) = column_type {
        entries.push(("type", text(column_type)));
    }
    map(entries)
}

struct SchemaErrorTestCase {
    description: &'static str,
    document: Node,
    in_seeds_directory: bool,
    expected_message: &'static str,
}

#[test]
fn given_invalid_schema_documents_when_parsing_then_reports_python_messages() {
    let test_cases = [
        SchemaErrorTestCase {
            description: "a document that is not a mapping",
            document: Node::List(Vec::new()),
            in_seeds_directory: true,
            expected_message: "/project/seeds/countries.yml must contain a top-level mapping",
        },
        SchemaErrorTestCase {
            description: "model metadata in YAML",
            document: map(vec![(
                "models",
                Node::List(vec![map(vec![("name", text("orders"))])]),
            )]),
            in_seeds_directory: false,
            expected_message: "/project/seeds/countries.yml declares model metadata in 'models', but model metadata must live in the model file MODEL(...). Move description, columns, and audits into the model header.",
        },
        SchemaErrorTestCase {
            description: "seeds outside the seeds directory",
            document: seed(vec![column("code", Some("VARCHAR"))], Vec::new()),
            in_seeds_directory: false,
            expected_message: "/project/seeds/countries.yml declares seeds, but seed declarations must live under seeds/**/*.yml",
        },
        SchemaErrorTestCase {
            description: "a seed column without a type",
            document: seed(vec![column("code", None)], Vec::new()),
            in_seeds_directory: true,
            expected_message: "/project/seeds/countries.yml seed column 'code' must define non-empty string 'type'",
        },
        SchemaErrorTestCase {
            description: "null audits are not an empty list",
            document: seed(
                vec![column("code", Some("VARCHAR"))],
                vec![("audits", Node::Null)],
            ),
            in_seeds_directory: true,
            expected_message: "/project/seeds/countries.yml seed audits must be a list",
        },
        SchemaErrorTestCase {
            description: "a non-boolean csv setting",
            document: seed(
                vec![column("code", Some("VARCHAR"))],
                vec![("csv_settings", map(vec![("doublequote", Node::Int(1))]))],
            ),
            in_seeds_directory: true,
            expected_message: "/project/seeds/countries.yml seed csv_settings 'doublequote' must be a boolean",
        },
    ];
    for test_case in test_cases {
        let error = parse_schema_document(&test_case.document, PATH, test_case.in_seeds_directory)
            .expect_err(test_case.description);
        assert_eq!(
            error.message, test_case.expected_message,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_valid_seed_document_when_parsing_then_keeps_authored_values() {
    let document = seed(
        vec![
            column("code", Some("VARCHAR")),
            column("label", Some("VARCHAR")),
        ],
        vec![("tags", Node::List(vec![text("reference")]))],
    );

    let seeds = parse_schema_document(&document, PATH, true).unwrap();

    assert_eq!(seeds.len(), 1);
    assert_eq!(seeds[0].name, text("countries"));
    assert_eq!(seeds[0].columns.len(), 2);
    assert_eq!(seeds[0].tags, vec![text("reference")]);
    assert!(seeds[0].csv_settings.is_none());
}
