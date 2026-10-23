use crate::refactoring::_helpers::contracts::model_types::declared_type_span;
use crate::refactoring::_helpers::scanning::chars::{chars, find};
use crate::refactoring::main::edit_model_contract::edit_model_contract;
use crate::refactoring::main::edit_source_contract::edit_source_contract;
use crate::refactoring::models::{
    ContractEdit, ContractModelColumn, ContractModelRequest, ContractSourceRequest,
};
use crate::refactoring::tests::helpers::physical_columns;
use crate::refactoring::tests::test_types::{
    DeclaredTypeSpanTestCase, ModelContractTestCase, SourceContractTestCase,
};

const HEADER: &str = "MODEL (\n  name m,\n  columns (\n    id (description 'key'),\n    amount (audits [custom(type INT)], type DECIMAL(10, 2)),\n    old (not_null true)\n  )\n);\nSELECT 1";
const SOURCES: &str = "sources:\n  - name: orders\n    columns:\n      - name: id\n        type: INT # key\n      - name: gone\n        type: TEXT\n  - name: other\n";

#[test]
fn given_nested_type_key_when_locating_declared_type_then_returns_top_level_value() {
    let test_cases = [
        DeclaredTypeSpanTestCase {
            description: "a nested type argument precedes the declared column type",
            contents: "amount (audits [custom(type INT)], type INT)",
            declared_type: "INT",
            expected_span: Some((40, 43)),
        },
        DeclaredTypeSpanTestCase {
            description: "a triple-quoted description with quotes and a type word is skipped",
            contents: "amount (description \"\"\"x \"type INT\" y\"\"\", type INT)",
            declared_type: "INT",
            expected_span: Some((47, 50)),
        },
        DeclaredTypeSpanTestCase {
            description: "a description ending in a backslash is skipped",
            contents: "amount (description \"under C:\\\", type INT)",
            declared_type: "INT",
            expected_span: Some((38, 41)),
        },
        DeclaredTypeSpanTestCase {
            description: "a quoted type matches after unescaping",
            contents: "amount (type 'a\\'b')",
            declared_type: "a'b",
            expected_span: Some((13, 19)),
        },
        DeclaredTypeSpanTestCase {
            description: "a type naming another value has no span",
            contents: "amount (type TEXT)",
            declared_type: "INT",
            expected_span: None,
        },
    ];

    for test_case in test_cases {
        let text = chars(test_case.contents);
        let metadata = (find(&text, "(", 0).unwrap_or_default() + 1, text.len() - 1);

        let span = declared_type_span(&text, metadata, test_case.declared_type);

        assert_eq!(span, test_case.expected_span, "{}", test_case.description);
    }
}

#[test]
fn given_physical_columns_when_editing_model_contract_then_header_matches_python() {
    let test_cases = [
        ModelContractTestCase {
            description: "overwrite types, drops, renders and appends columns",
            contents: HEADER,
            columns: &[("id", None), ("amount", Some("DECIMAL(10,2)")), ("old", Some("INT"))],
            dynamic_patterns: &[],
            physical: &[
                ("ID", "BIGINT"),
                ("amount", "DOUBLE"),
                ("region_a", "TEXT"),
                ("note", "STRUCT(a INT)"),
            ],
            overwrite: true,
            expected_edit: ContractEdit::Edited(
                "MODEL (\n  name m,\n  columns (\n    id (type BIGINT, description 'key'),\n    amount (audits [custom(type INT)], type DOUBLE),\n    \n  \n    region_a (type TEXT)\n    note (type \"STRUCT(a INT)\")\n  )\n);\nSELECT 1".to_owned(),
            ),
        },
        ModelContractTestCase {
            description: "dynamic family members are not frozen into the contract",
            contents: HEADER,
            columns: &[("id", None), ("amount", Some("DECIMAL(10,2)")), ("old", Some("INT"))],
            dynamic_patterns: &[Some("region_.*")],
            physical: &[("id", "INT"), ("region_a", "TEXT")],
            overwrite: false,
            expected_edit: ContractEdit::Edited(HEADER.replacen("id (description", "id (type INT, description", 1)),
        },
        ModelContractTestCase {
            description: "a header without columns gains a columns block",
            contents: "MODEL (name m);\nSELECT 1",
            columns: &[],
            dynamic_patterns: &[],
            physical: &[("id", "INT"), ("a b", "x\"y")],
            overwrite: false,
            expected_edit: ContractEdit::Edited(
                "MODEL (name m\n  columns (\n    id (type INT)\n    a b (type \"x\\\"y\")\n  ));\nSELECT 1".to_owned(),
            ),
        },
        ModelContractTestCase {
            description: "a declared column without an entry span is a conflict",
            contents: HEADER,
            columns: &[("missing", None)],
            dynamic_patterns: &[],
            physical: &[],
            overwrite: false,
            expected_edit: ContractEdit::Conflict(
                "column 'missing' has no unambiguous authored span".to_owned(),
            ),
        },
    ];

    for test_case in test_cases {
        let request = ContractModelRequest {
            contents: test_case.contents.to_owned(),
            relative_path: "m.sql".to_owned(),
            shared_schema: false,
            columns: test_case
                .columns
                .iter()
                .map(|(name, declared_type)| ContractModelColumn {
                    name: (*name).to_owned(),
                    declared_type: declared_type.map(str::to_owned),
                    location_path: None,
                })
                .collect(),
            dynamic_patterns: test_case
                .dynamic_patterns
                .iter()
                .map(|pattern| pattern.map(str::to_owned))
                .collect(),
            physical_columns: physical_columns(test_case.physical),
            overwrite: test_case.overwrite,
        };

        let edit = edit_model_contract(&request);

        assert_eq!(
            edit,
            Ok(test_case.expected_edit),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_physical_columns_when_editing_source_contract_then_yaml_matches_python() {
    let test_cases = [
        SourceContractTestCase {
            description: "overwrite retypes with the comment kept, drops and appends",
            contents: SOURCES,
            columns: &[("id", Some("INT")), ("gone", Some("TEXT"))],
            physical: &[("id", "BIGINT"), ("note", "it's")],
            overwrite: true,
            expected_edit: ContractEdit::Edited(
                "sources:\n  - name: orders\n    columns:\n      - name: id\n        type: 'BIGINT' # key\n      - name: note\n        type: 'it''s'\n  - name: other\n".to_owned(),
            ),
        },
        SourceContractTestCase {
            description: "a source without columns gains a columns key",
            contents: "sources:\n- name: orders\n  schema: raw\n",
            columns: &[],
            physical: &[("id", "INT")],
            overwrite: false,
            expected_edit: ContractEdit::Edited(
                "sources:\n- name: orders\n  schema: raw\n  columns:\n    - name: id\n      type: 'INT'\n".to_owned(),
            ),
        },
        SourceContractTestCase {
            description: "a generated file is never edited",
            contents: "# Generated file\nsources:\n- name: orders\n",
            columns: &[],
            physical: &[("id", "INT")],
            overwrite: false,
            expected_edit: ContractEdit::Conflict("source file is marked as generated".to_owned()),
        },
    ];

    for test_case in test_cases {
        let request = ContractSourceRequest {
            contents: test_case.contents.to_owned(),
            discovered_contents: test_case.contents.to_owned(),
            name: "orders".to_owned(),
            columns: test_case
                .columns
                .iter()
                .map(|(name, declared_type)| ((*name).to_owned(), declared_type.map(str::to_owned)))
                .collect(),
            physical_columns: physical_columns(test_case.physical),
            overwrite: test_case.overwrite,
        };

        let edit = edit_source_contract(&request);

        assert_eq!(edit, test_case.expected_edit, "{}", test_case.description);
    }
}
