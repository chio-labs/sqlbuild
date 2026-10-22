use crate::dsl_headers::_helpers::quoted::decode_description;
use crate::dsl_headers::_helpers::wrap::wrap_description;
use crate::dsl_headers::main::format_headers::format_headers;
use crate::dsl_headers::main::measurement_body_ranges::measurement_body_ranges;
use crate::dsl_headers::main::scan_headers::scan_headers;
use crate::dsl_headers::main::sql_body_ranges::sql_body_ranges;
use crate::dsl_headers::models::HeaderRulesConfig;
use crate::dsl_headers::tests::helpers::chars;
use crate::dsl_headers::tests::test_types::{
    CompactParser, FormatTestCase, ProseTestCase, ScanTestCase,
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
fn given_description_text_when_wrapping_and_decoding_then_matches_python() {
    let test_cases = [ProseTestCase {
        description: "paragraphs, an unbreakable word and every escape form",
        prose: "  The  orders\tmodel joins every customer to supercalifragilisticexpialidociously long words.\n \n Second   paragraph here.",
        escaped: r#"a\"b\\c\nd\u00e9\U0001F600\uD800\x"#,
        expected_wrapped: "The orders model\njoins every customer to\nsupercalifragilisticexpialidociously\nlong words.\n\nSecond paragraph here.",
        expected_decoded: "a\"b\\c\nd\u{e9}\u{1f600}\\uD800\\x",
    }];

    for test_case in test_cases {
        let wrapped: String = wrap_description(&chars(test_case.prose), 20, 30)
            .into_iter()
            .collect();
        let decoded: String = decode_description(&chars(test_case.escaped), '"')
            .into_iter()
            .collect();

        assert_eq!(
            wrapped, test_case.expected_wrapped,
            "{}",
            test_case.description
        );
        assert_eq!(
            decoded, test_case.expected_decoded,
            "{}",
            test_case.description
        );
    }
}
