use crate::dsl_headers::_helpers::wrap::wrap_description;
use crate::dsl_headers::main::fix_escaped_quotes::fix_escaped_quotes;
use crate::dsl_headers::main::format_headers::format_headers;
use crate::dsl_headers::main::measurement_body_ranges::measurement_body_ranges;
use crate::dsl_headers::main::scan_headers::scan_headers;
use crate::dsl_headers::main::sql_body_ranges::sql_body_ranges;
use crate::dsl_headers::models::HeaderRulesConfig;
use crate::dsl_headers::tests::helpers::{chars, lint_codes, stored_descriptions};
use crate::dsl_headers::tests::test_types::{
    CompactParser, FormatTestCase, LengthTestCase, NativeParser, ProseTestCase, QuoteFixTestCase,
    ScanTestCase,
};

const MODEL_FILE: &str = "-- leading note\n-- second line\nMODEL (\n  name orders,   \n  audits [not_null(column 'order_id'), unique(column 'order_id'), accepted_values(column 'status', values ['a', 'b'])]\n);\nSELECT 1 /* MODEL ( */ , 'MODEL (x)'\n  TEST (\"a\\\")\" ) ;\nSELECT 2\n";

#[test]
fn given_sql_file_when_scanning_headers_then_matches_python_spans_and_bodies() {
    let test_cases = [
        ScanTestCase {
            description: "headers past comments and strings, with an escaped quote",
            text: MODEL_FILE,
            expected_spans: vec![("MODEL", 31, 178), ("TEST", 218, 234)],
            expected_bodies: vec![(0, 31), (179, 218), (235, 244)],
            expected_measurements: vec![],
        },
        ScanTestCase {
            description: "a measurement block body and an empty evidence block",
            text: "AUDIT (name x);\nMEASURE (\n  SELECT 1\n)\nEVIDENCE ( )\n",
            expected_spans: vec![("AUDIT", 0, 15)],
            expected_bodies: vec![(16, 52)],
            expected_measurements: vec![(28, 37)],
        },
    ];

    for test_case in test_cases {
        let text: Vec<char> = chars(test_case.text);
        let headers = scan_headers(&text, false);
        let spans: Vec<(&str, usize, usize)> = headers
            .iter()
            .map(|header| (header.kind.as_str(), header.start, header.end))
            .collect();

        assert_eq!(spans, test_case.expected_spans, "{}", test_case.description);
        assert_eq!(
            sql_body_ranges(&text, &headers),
            test_case.expected_bodies,
            "{}",
            test_case.description
        );
        assert_eq!(
            measurement_body_ranges(&text),
            test_case.expected_measurements,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_model_header_when_formatting_then_matches_python_rewrite() {
    let test_cases = [FormatTestCase {
        description: "a leading comment moves into the description and long audits explode",
        text: MODEL_FILE,
        line_width: 60,
        expected_text: "MODEL (\n  description \"leading note second line\",\n  name orders,\n  audits [\n    not_null(column 'order_id'),\n    unique(column 'order_id'),\n    accepted_values(column 'status', values ['a', 'b']),\n  ]\n);\nSELECT 1 /* MODEL ( */ , 'MODEL (x)'\n  TEST (\"a\\\")\" ) ;\nSELECT 2\n",
    }];

    for test_case in test_cases {
        let config = HeaderRulesConfig {
            line_width: test_case.line_width,
            max_description_lines: 10,
        };
        let Ok((formatted, _faults)) =
            format_headers(&chars(test_case.text), config, &CompactParser);

        assert_eq!(
            formatted.iter().collect::<String>(),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_sql_macro_headers_when_formatting_then_each_is_laid_out_canonically_and_stays_so() {
    let test_cases = [
        FormatTestCase {
            description: "a one-line header that fits keeps one line with normalised spacing",
            text: "MACRO (description \"Net\",   arguments (a BIGINT,b BIGINT ), returns DECIMAL(18,2));\n\n@a\n",
            line_width: 100,
            expected_text: "MACRO (description \"Net\", arguments (a BIGINT, b BIGINT), returns DECIMAL(18, 2));\n\n@a\n",
        },
        FormatTestCase {
            description: "a multi-line header puts one item per line and breaks a list too wide",
            text: "MACRO (description \"Latest row per key\",\n arguments (src RELATION (updated_at TIMESTAMP), key COLUMN OF src));\n\nWITH x AS (SELECT 1)\n",
            line_width: 50,
            expected_text: "MACRO (\n  description \"Latest row per key\",\n  arguments (\n    src RELATION (updated_at TIMESTAMP),\n    key COLUMN OF src,\n  ),\n);\n\nWITH x AS (SELECT 1)\n",
        },
        FormatTestCase {
            description: "a header with a comment is left as authored",
            text: "MACRO (description \"X\",  -- note\n  returns BIGINT);\n\n1\n",
            line_width: 100,
            expected_text: "MACRO (description \"X\",  -- note\n  returns BIGINT);\n\n1\n",
        },
    ];

    for test_case in test_cases {
        let config = HeaderRulesConfig {
            line_width: test_case.line_width,
            max_description_lines: 10,
        };
        let Ok((formatted, _)) = format_headers(&chars(test_case.text), config, &CompactParser);
        let Ok((again, _)) = format_headers(&formatted, config, &CompactParser);

        assert_eq!(
            formatted.iter().collect::<String>(),
            test_case.expected_text,
            "{}",
            test_case.description
        );
        assert_eq!(again, formatted, "{}", test_case.description);
    }
}

#[test]
fn given_description_text_when_wrapping_then_matches_python() {
    let test_cases = [ProseTestCase {
        description: "paragraphs and an unbreakable word",
        prose: "  The  orders\tmodel joins every customer to supercalifragilisticexpialidociously long words.\n \n Second   paragraph here.",
        expected_wrapped: "The orders model\njoins every customer to\nsupercalifragilisticexpialidociously\nlong words.\n\nSecond paragraph here.",
    }];

    for test_case in test_cases {
        let wrapped: String = wrap_description(&chars(test_case.prose), 20, 30)
            .into_iter()
            .collect();

        assert_eq!(
            wrapped, test_case.expected_wrapped,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_descriptions_when_formatting_then_layout_is_canonical_idempotent_and_text_unchanged() {
    let test_cases = [
        FormatTestCase {
            description: "a short wrapped description is joined onto one line",
            text: "MODEL (\n  description \"Orders placed\n  by day.\",\n  materialized table,\n);\nSELECT 1\n",
            line_width: 100,
            expected_text: "MODEL (\n  description \"Orders placed by day.\",\n  materialized table,\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "a description that fits stays one line",
            text: "MODEL (\n  description \"Orders placed by day.\",\n);\nSELECT 1\n",
            line_width: 100,
            expected_text: "MODEL (\n  description \"Orders placed by day.\",\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "a long description becomes an indented block wrapped at the width",
            text: "MODEL (\n  description \"True when a name starts with a woman's title: Mme, Mlle, Miss, Mrs, Ms. Any case, with or without a dot.\",\n  materialized table,\n);\nSELECT 1\n",
            line_width: 60,
            expected_text: "MODEL (\n  description \"\"\"\n    True when a name starts with a woman's title: Mme, Mlle,\n    Miss, Mrs, Ms. Any case, with or without a dot.\n  \"\"\",\n  materialized table,\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "continuation lines at column zero become a block",
            text: "MODEL (\n  description \"True when a name starts with a woman's title: Mme, Mlle, Miss, Mrs, Ms. Any case,\nwith or without a dot ('MISS ANNA PARKER', 'Mrs. C. O'Brien', 'Ms.Robinson').\",\n);\nSELECT 1\n",
            line_width: 100,
            expected_text: "MODEL (\n  description \"\"\"\n    True when a name starts with a woman's title: Mme, Mlle, Miss, Mrs, Ms. Any case, with or\n    without a dot ('MISS ANNA PARKER', 'Mrs. C. O'Brien', 'Ms.Robinson').\n  \"\"\",\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "a short description with double quotes uses one-line triple quotes",
            text: "MODEL (\n  description 'Matches \"Miss\".',\n);\nSELECT 1\n",
            line_width: 100,
            expected_text: "MODEL (\n  description \"\"\"Matches \"Miss\".\"\"\",\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "a long description with double quotes becomes a block",
            text: "MODEL (\n  description \"\"\"True when a name starts with a title, with or without a dot (\"MISS ANNA PARKER\", \"Mrs. C. O'Brien\").\"\"\",\n);\nSELECT 1\n",
            line_width: 80,
            expected_text: "MODEL (\n  description \"\"\"\n    True when a name starts with a title, with or without a dot (\"MISS ANNA\n    PARKER\", \"Mrs. C. O'Brien\").\n  \"\"\",\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "paragraphs stay separated by a blank line",
            text: "MODEL (\n  description \"First paragraph about orders.\n\n  Second paragraph about refunds.\",\n);\nSELECT 1\n",
            line_width: 100,
            expected_text: "MODEL (\n  description \"\"\"\n    First paragraph about orders.\n\n    Second paragraph about refunds.\n  \"\"\",\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "a one-line triple-quoted description without quotes becomes plain",
            text: "MODEL (\n  description \"\"\"Orders by day.\"\"\",\n);\nSELECT 1\n",
            line_width: 100,
            expected_text: "MODEL (\n  description \"Orders by day.\",\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "a one-line single-quoted description that fits is kept",
            text: "MODEL (\n  description 'Orders by day.',\n);\nSELECT 1\n",
            line_width: 100,
            expected_text: "MODEL (\n  description 'Orders by day.',\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "an escaped quote is left for format --fix",
            text: "MODEL (\n  description \"Matches \\\"Miss\\\".\",\n);\nSELECT 1\n",
            line_width: 100,
            expected_text: "MODEL (\n  description \"Matches \\\"Miss\\\".\",\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "a long MACRO description becomes a block under its laid-out header",
            text: "MACRO (description \"True when a name starts with a woman's title: Mme, Mlle, Miss, Mrs, Ms. Any case.\", arguments (value VARCHAR), returns BOOLEAN);\n\n@value IS NOT NULL\n",
            line_width: 60,
            expected_text: "MACRO (\n  description \"\"\"\n    True when a name starts with a woman's title: Mme, Mlle,\n    Miss, Mrs, Ms. Any case.\n  \"\"\",\n  arguments (value VARCHAR),\n  returns BOOLEAN,\n);\n\n@value IS NOT NULL\n",
        },
        FormatTestCase {
            description: "a long MACRO description with a doubled quote keeps its text",
            text: "MACRO (\n  description 'it''s a word word word word word word word word word end',\n  arguments (v VARCHAR),\n  returns VARCHAR,\n);\n\nLOWER(@v)\n",
            line_width: 50,
            expected_text: "MACRO (\n  description \"\"\"\n    it's a word word word word word word word word\n    word end\n  \"\"\",\n  arguments (v VARCHAR),\n  returns VARCHAR,\n);\n\nLOWER(@v)\n",
        },
        FormatTestCase {
            description: "a long model description with an escaped single quote keeps its text",
            text: "MODEL (\n  description 'it\\'s a word word word word word word word word word end',\n);\nSELECT 1\n",
            line_width: 50,
            expected_text: "MODEL (\n  description \"\"\"\n    it's a word word word word word word word word\n    word end\n  \"\"\",\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "a description ending in a backslash stays as written",
            text: "MODEL (\n  description \"Files under C:\\\",\n);\nSELECT 1\n",
            line_width: 100,
            expected_text: "MODEL (\n  description \"Files under C:\\\",\n);\nSELECT 1\n",
        },
        FormatTestCase {
            description: "a short description stays when later fields make its line long",
            text: "FUNCTION (description 'Test function is_large_order.', arguments (amount_cents INTEGER), returns BOOLEAN);\n\namount_cents > 100\n",
            line_width: 100,
            expected_text: "FUNCTION (description 'Test function is_large_order.', arguments (amount_cents INTEGER), returns BOOLEAN);\n\namount_cents > 100\n",
        },
        FormatTestCase {
            description: "a description too long by itself becomes a block before later fields",
            text: "FUNCTION (description \"Whether an order is large enough to need review.\", returns BOOLEAN);\n\nTRUE\n",
            line_width: 50,
            expected_text: "FUNCTION (description \"\"\"\n  Whether an order is large enough to need review.\n\"\"\", returns BOOLEAN);\n\nTRUE\n",
        },
        FormatTestCase {
            description: "a SCHEMA description is laid out",
            text: "SCHEMA (\n  name order_columns,\n  description \"Columns every\n  order model shares.\",\n  columns (order_id (type BIGINT)),\n);\n",
            line_width: 100,
            expected_text: "SCHEMA (\n  name order_columns,\n  description \"Columns every order model shares.\",\n  columns (order_id (type BIGINT)),\n);\n",
        },
    ];

    for test_case in test_cases {
        let config = HeaderRulesConfig {
            line_width: test_case.line_width,
            max_description_lines: 10,
        };
        let text: Vec<char> = chars(test_case.text);
        let Ok((formatted, _)) = format_headers(&text, config, &NativeParser);
        let Ok((again, _)) = format_headers(&formatted, config, &NativeParser);

        assert_eq!(
            formatted.iter().collect::<String>(),
            test_case.expected_text,
            "{}",
            test_case.description
        );
        assert_eq!(again, formatted, "idempotent: {}", test_case.description);
        assert_eq!(
            stored_descriptions(&formatted),
            stored_descriptions(&text),
            "stored text unchanged: {}",
            test_case.description
        );
    }
}

#[test]
fn given_escaped_quotes_in_descriptions_when_fixing_then_triple_quotes_hold_real_quotes() {
    let test_cases = [
        QuoteFixTestCase {
            description: "a model description",
            text: "MODEL (\n  description \"Matches a title (\\\"Miss\\\").\",\n);\nSELECT 1\n",
            expected_text: "MODEL (\n  description \"\"\"Matches a title (\"Miss\").\"\"\",\n);\nSELECT 1\n",
            expected_lines: vec![2],
        },
        QuoteFixTestCase {
            description: "a wrapped macro description with apostrophes",
            text: "MACRO (\n  description \"A woman's title,\nwith a dot (\\\"Mrs. C. O'Brien\\\").\",\n  returns VARCHAR,\n);\n'x'\n",
            expected_text: "MACRO (\n  description \"\"\"A woman's title,\nwith a dot (\"Mrs. C. O'Brien\").\"\"\",\n  returns VARCHAR,\n);\n'x'\n",
            expected_lines: vec![2],
        },
        QuoteFixTestCase {
            description: "a column description, and text ending in a quote",
            text: "MODEL (\n  description \"Orders.\",\n  columns (title (description \"Says \\\"hi\\\"\")),\n);\nSELECT 1\n",
            expected_text: "MODEL (\n  description \"Orders.\",\n  columns (title (description \"\"\"Says \"hi\"\"\"\")),\n);\nSELECT 1\n",
            expected_lines: vec![3],
        },
        QuoteFixTestCase {
            description: "doubled quotes in a model description",
            text: "MODEL (\n  description \"say \"\"hi\"\" now\",\n);\nSELECT 1\n",
            expected_text: "MODEL (\n  description \"\"\"say \"hi\" now\"\"\",\n);\nSELECT 1\n",
            expected_lines: vec![2],
        },
        QuoteFixTestCase {
            description: "doubled quotes in a macro description",
            text: "MACRO (\n  description \"say \"\"hi\"\" now\",\n  returns VARCHAR,\n);\n'x'\n",
            expected_text: "MACRO (\n  description \"\"\"say \"hi\" now\"\"\",\n  returns VARCHAR,\n);\n'x'\n",
            expected_lines: vec![2],
        },
        QuoteFixTestCase {
            description: "a description that already reads is left alone",
            text: "MODEL (\n  description \"Files under C:\\\",\n);\nSELECT 1\n",
            expected_text: "MODEL (\n  description \"Files under C:\\\",\n);\nSELECT 1\n",
            expected_lines: vec![],
        },
        QuoteFixTestCase {
            description: "another backslash escape is not rewritten",
            text: "MODEL (\n  description \"Path C:\\\\data \\\"x\\\"\",\n);\nSELECT 1\n",
            expected_text: "MODEL (\n  description \"Path C:\\\\data \\\"x\\\"\",\n);\nSELECT 1\n",
            expected_lines: vec![],
        },
        QuoteFixTestCase {
            description: "text that would hold three quotes in a row is not rewritten",
            text: "MODEL (\n  description \"a \\\"\\\"\\\" b\",\n);\nSELECT 1\n",
            expected_text: "MODEL (\n  description \"a \\\"\\\"\\\" b\",\n);\nSELECT 1\n",
            expected_lines: vec![],
        },
        QuoteFixTestCase {
            description: "a SQL string that escapes a quote is left alone",
            text: "MODEL (\n  description \"Orders.\",\n  audits [expression(predicate \"name <> \\\"x\\\"\")],\n);\nSELECT 1\n",
            expected_text: "MODEL (\n  description \"Orders.\",\n  audits [expression(predicate \"name <> \\\"x\\\"\")],\n);\nSELECT 1\n",
            expected_lines: vec![],
        },
    ];

    for test_case in test_cases {
        let (fixed, lines) = fix_escaped_quotes(&chars(test_case.text));

        assert_eq!(
            fixed.iter().collect::<String>(),
            test_case.expected_text,
            "{}",
            test_case.description
        );
        assert_eq!(lines, test_case.expected_lines, "{}", test_case.description);
    }
}

#[test]
fn given_description_near_the_line_limit_when_linting_then_block_layout_counts_as_before() {
    let words: &str =
        "aaaa bbbb cccc dddd eeee ffff gggg hhhh iiii jjjj kkkk llll mmmm nnnn oooo pppp qqqq rrrr";
    let test_cases = [
        LengthTestCase {
            description: "three lines wide at the full width stay within the limit",
            text: format!("MODEL (\n  description \"{words}\",\n);\nSELECT 1\n"),
            expected_too_long: false,
        },
        LengthTestCase {
            description: "the same words laid out as an indented block stay within the limit",
            text: "MODEL (\n  description \"\"\"\n    aaaa bbbb cccc dddd eeee ffff gggg\n    hhhh iiii jjjj kkkk llll mmmm nnnn\n    oooo pppp qqqq rrrr\n  \"\"\",\n);\nSELECT 1\n"
                .to_owned(),
            expected_too_long: false,
        },
        LengthTestCase {
            description: "more words than fit in three lines exceed the limit",
            text: format!(
                "MODEL (\n  description \"{words} ssss tttt uuuu vvvv\",\n);\nSELECT 1\n"
            ),
            expected_too_long: true,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            lint_codes(&test_case.text, (40, 3)).contains(&"description-length"),
            test_case.expected_too_long,
            "{}",
            test_case.description
        );
    }
}
