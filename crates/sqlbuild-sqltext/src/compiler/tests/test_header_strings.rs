use crate::compiler::_helpers::model_headers::tokenization::parse_one;
use crate::compiler::models::AuthoredValue;
use crate::compiler::tests::test_types::HeaderStringTestCase;

/// The string at `path`: map keys, call names, or list indexes in brackets.
fn string_at(value: &AuthoredValue, path: &[&str]) -> Option<String> {
    let Some((first, rest)) = path.split_first() else {
        return match value {
            AuthoredValue::String(text) => Some(text.clone()),
            _ => None,
        };
    };
    let next: &AuthoredValue = match value {
        AuthoredValue::Map(entries) => &entries.iter().find(|(key, _)| key == first)?.1,
        AuthoredValue::List(items) => {
            let index: usize = first.trim_matches(['[', ']']).parse().ok()?;
            items.get(index)?
        }
        _ => return None,
    };
    string_at(next, rest)
}

#[test]
fn given_header_strings_when_parsing_then_prose_is_folded_and_other_text_kept_as_written() {
    let test_cases = [
        HeaderStringTestCase {
            description: "a wrapped description is folded",
            header: "description \"Orders placed\nby day, one row each.\"",
            path: &["description"],
            expected: Ok("Orders placed by day, one row each."),
        },
        HeaderStringTestCase {
            description: "a triple-quoted description on one line keeps its quotes",
            header: r#"description """Matches "Miss".""", materialized table"#,
            path: &["description"],
            expected: Ok(r#"Matches "Miss"."#),
        },
        HeaderStringTestCase {
            description: "a triple-quoted block is folded with paragraphs",
            header: "description \"\"\"\n    A \"quoted\" word,\n    it's fine.\n\n    Second.\n  \"\"\",\n  materialized table",
            path: &["description"],
            expected: Ok("A \"quoted\" word, it's fine.\n\nSecond."),
        },
        HeaderStringTestCase {
            description: "the same text on one line or wrapped stores the same",
            header: "description \"True for a woman's title: Mme, Mlle,\n  Miss (any case).\"",
            path: &["description"],
            expected: Ok("True for a woman's title: Mme, Mlle, Miss (any case)."),
        },
        HeaderStringTestCase {
            description: "a column description is prose",
            header: "columns (order_id (type BIGINT, description \"The order\n  key.\"))",
            path: &["columns", "order_id", "description"],
            expected: Ok("The order key."),
        },
        HeaderStringTestCase {
            description: "an audit's description option is prose",
            header: "audits [not_null(column 'id', description \"Every row\n  has one.\")]",
            path: &["audits", "[0]", "not_null", "description"],
            expected: Ok("Every row has one."),
        },
        HeaderStringTestCase {
            description: "a meta value keeps its line breaks",
            header: "meta (description \"kept\n  as written\")",
            path: &["meta", "description"],
            expected: Ok("kept\n  as written"),
        },
        HeaderStringTestCase {
            description: "an audit predicate keeps its line breaks",
            header: "audits [expression(predicate \"a > 0\n  AND b > 0\")]",
            path: &["audits", "[0]", "expression", "predicate"],
            expected: Ok("a > 0\n  AND b > 0"),
        },
        HeaderStringTestCase {
            description: "a triple-quoted SQL string keeps backslashes and quotes",
            header: r#"name_pattern """^"x"\d+$""""#,
            path: &["name_pattern"],
            expected: Ok(r#"^"x"\d+$"#),
        },
        HeaderStringTestCase {
            description: "a non-prose string still reads backslash escapes",
            header: r#"name_pattern "a\"b""#,
            path: &["name_pattern"],
            expected: Ok("a\"b"),
        },
        HeaderStringTestCase {
            description: "an escaped double quote in a description fails at the quote",
            header: r#"description "Matches a title (\"Miss\").""#,
            path: &["description"],
            expected: Err(r#"double quote inside a "..." string at position 31"#),
        },
        HeaderStringTestCase {
            description: "a wrapped escaped quote with apostrophes fails the same way",
            header: "description \"A woman's title, with or without a dot\n(\\\"MISS SARAH BOWEN\\\", \\\"Mrs. C. O'Leary\\\").\"",
            path: &["description"],
            expected: Err(r#"double quote inside a "..." string at position 54"#),
        },
        HeaderStringTestCase {
            description: "a bare double quote ends the string where text runs on",
            header: r#"description "Matches "Miss" here""#,
            path: &["description"],
            expected: Err(r#"double quote inside a "..." string at position 21"#),
        },
        HeaderStringTestCase {
            description: "a triple quote inside a triple-quoted string",
            header: r#"description """He said """hi""" then""""#,
            path: &["description"],
            expected: Err(r#"""" inside a """...""" string at position 23"#),
        },
        HeaderStringTestCase {
            description: "a triple quote inside, followed by more text on the line",
            header: r#"description """a """ b""""#,
            path: &["description"],
            expected: Err(r#"""" inside a """...""" string at position 17"#),
        },
        HeaderStringTestCase {
            description: "an unclosed triple-quoted string reports where it started",
            header: "description \"\"\"\n  never closed\n",
            path: &["description"],
            expected: Err(r#"unclosed """ string starting at position 12"#),
        },
    ];

    for test_case in test_cases {
        let (value, _, error) = parse_one(test_case.header);
        let actual: Result<String, String> = match (value, error) {
            (_, Some(error)) => Err(error),
            (Some(value), None) => string_at(&value, test_case.path)
                .ok_or_else(|| format!("no string at {:?}", test_case.path)),
            (None, None) => Err("no value and no error".to_owned()),
        };
        assert_eq!(
            actual,
            test_case.expected.map(str::to_owned).map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
