use crate::json::_helpers::floats::python_repr;
use crate::json::errors::JsonEmitError;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonInteger, OrjsonOptions, StdlibJsonOptions};
use crate::json::tests::helpers::{
    digits, lone_surrogate_text, nested_arrays, non_finite_floats, sample_document,
};
use crate::json::tests::test_types::{DumpsTestCase, FloatReprTestCase, IntegerParseTestCase};

const BIG: &str = "1180591620717411303424";
const U64_MAX: &str = "18446744073709551615";

#[test]
fn given_python_serializer_options_when_dumping_then_output_matches_python_bytes() {
    let stdlib_compact_sorted = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    };
    let stdlib_unicode_indented = StdlibJsonOptions {
        ensure_ascii: false,
        sort_keys: true,
        ..StdlibJsonOptions::new(Some(2))
    };
    let test_cases = [
        DumpsTestCase {
            description: "json.dumps defaults",
            value: sample_document(BIG),
            dialect: JsonDialect::Stdlib(StdlibJsonOptions::new(None)),
            expected_text: Ok(
                r#"{"name": "caf\u00e9 \u2615 \ud83d\ude00", "control": "\u0000\u001f\u007f\t\n\"\\/", "ints": [0, -1, 9223372036854775808, 1180591620717411303424], "floats": [0.1, -0.0, 1e+16, 1e-05, 2.5e-07, 1000000000000000.0, 100.0], "empty": [{}, []], "z": null, "a": true}"#,
            ),
        },
        DumpsTestCase {
            description: "json.dumps indent=2",
            value: sample_document(BIG),
            dialect: JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2))),
            expected_text: Ok(
                "{\n  \"name\": \"caf\\u00e9 \\u2615 \\ud83d\\ude00\",\n  \"control\": \"\\u0000\\u001f\\u007f\\t\\n\\\"\\\\/\",\n  \"ints\": [\n    0,\n    -1,\n    9223372036854775808,\n    1180591620717411303424\n  ],\n  \"floats\": [\n    0.1,\n    -0.0,\n    1e+16,\n    1e-05,\n    2.5e-07,\n    1000000000000000.0,\n    100.0\n  ],\n  \"empty\": [\n    {},\n    []\n  ],\n  \"z\": null,\n  \"a\": true\n}",
            ),
        },
        DumpsTestCase {
            description: "json.dumps compact sorted ASCII",
            value: sample_document(BIG),
            dialect: JsonDialect::Stdlib(stdlib_compact_sorted),
            expected_text: Ok(
                r#"{"a":true,"control":"\u0000\u001f\u007f\t\n\"\\/","empty":[{},[]],"floats":[0.1,-0.0,1e+16,1e-05,2.5e-07,1000000000000000.0,100.0],"ints":[0,-1,9223372036854775808,1180591620717411303424],"name":"caf\u00e9 \u2615 \ud83d\ude00","z":null}"#,
            ),
        },
        DumpsTestCase {
            description: "json.dumps ensure_ascii=False indent=2 sorted",
            value: sample_document(BIG),
            dialect: JsonDialect::Stdlib(stdlib_unicode_indented),
            expected_text: Ok(
                "{\n  \"a\": true,\n  \"control\": \"\\u0000\\u001f\u{7f}\\t\\n\\\"\\\\/\",\n  \"empty\": [\n    {},\n    []\n  ],\n  \"floats\": [\n    0.1,\n    -0.0,\n    1e+16,\n    1e-05,\n    2.5e-07,\n    1000000000000000.0,\n    100.0\n  ],\n  \"ints\": [\n    0,\n    -1,\n    9223372036854775808,\n    1180591620717411303424\n  ],\n  \"name\": \"café ☕ 😀\",\n  \"z\": null\n}",
            ),
        },
        DumpsTestCase {
            description: "orjson OPT_INDENT_2",
            value: sample_document(U64_MAX),
            dialect: JsonDialect::Orjson(OrjsonOptions {
                indent_2: true,
                sort_keys: false,
            }),
            expected_text: Ok(
                "{\n  \"name\": \"café ☕ 😀\",\n  \"control\": \"\\u0000\\u001f\u{7f}\\t\\n\\\"\\\\/\",\n  \"ints\": [\n    0,\n    -1,\n    9223372036854775808,\n    18446744073709551615\n  ],\n  \"floats\": [\n    0.1,\n    -0.0,\n    1e+16,\n    0.00001,\n    2.5e-7,\n    1000000000000000.0,\n    100.0\n  ],\n  \"empty\": [\n    {},\n    []\n  ],\n  \"z\": null,\n  \"a\": true\n}",
            ),
        },
        DumpsTestCase {
            description: "orjson OPT_SORT_KEYS",
            value: sample_document(U64_MAX),
            dialect: JsonDialect::Orjson(OrjsonOptions {
                indent_2: false,
                sort_keys: true,
            }),
            expected_text: Ok(
                "{\"a\":true,\"control\":\"\\u0000\\u001f\u{7f}\\t\\n\\\"\\\\/\",\"empty\":[{},[]],\"floats\":[0.1,-0.0,1e+16,0.00001,2.5e-7,1000000000000000.0,100.0],\"ints\":[0,-1,9223372036854775808,18446744073709551615],\"name\":\"café ☕ 😀\",\"z\":null}",
            ),
        },
        DumpsTestCase {
            description: "orjson rejects integers beyond 64 bits",
            value: sample_document(BIG),
            dialect: JsonDialect::Orjson(OrjsonOptions::default()),
            expected_text: Err(JsonEmitError::IntegerOutOfRange),
        },
        DumpsTestCase {
            description: "json.dumps writes NaN and infinities",
            value: non_finite_floats(),
            dialect: JsonDialect::Stdlib(StdlibJsonOptions::new(None)),
            expected_text: Ok("[NaN, Infinity, -Infinity]"),
        },
        DumpsTestCase {
            description: "json.dumps allow_nan=False rejects NaN",
            value: non_finite_floats(),
            dialect: JsonDialect::Stdlib(StdlibJsonOptions {
                allow_nan: false,
                ..StdlibJsonOptions::new(None)
            }),
            expected_text: Err(JsonEmitError::NonFiniteFloat),
        },
        DumpsTestCase {
            description: "orjson writes non-finite floats as null",
            value: non_finite_floats(),
            dialect: JsonDialect::Orjson(OrjsonOptions::default()),
            expected_text: Ok("[null,null,null]"),
        },
        DumpsTestCase {
            description: "json.dumps refuses integers beyond Python's string conversion limit",
            value: digits(4_301),
            dialect: JsonDialect::Stdlib(StdlibJsonOptions::new(None)),
            expected_text: Err(JsonEmitError::IntegerTooLong),
        },
        DumpsTestCase {
            description: "deeply nested values are refused instead of exhausting the stack",
            value: nested_arrays(1_000),
            dialect: JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2))),
            expected_text: Err(JsonEmitError::NestingTooDeep),
        },
        DumpsTestCase {
            description: "orjson refuses deeply nested values too",
            value: nested_arrays(130),
            dialect: JsonDialect::Orjson(OrjsonOptions::default()),
            expected_text: Err(JsonEmitError::NestingTooDeep),
        },
        DumpsTestCase {
            description: "json.dumps escapes lone surrogates beside escapes and a non-BMP pair",
            value: lone_surrogate_text(),
            dialect: JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2))),
            expected_text: Ok(r#""\"q\"\\\u00e9\udcff\ud83d\ude00\ud83d""#),
        },
        DumpsTestCase {
            description: "json.dumps ensure_ascii=False cannot write a lone surrogate as text",
            value: lone_surrogate_text(),
            dialect: JsonDialect::Stdlib(StdlibJsonOptions {
                ensure_ascii: false,
                ..StdlibJsonOptions::new(None)
            }),
            expected_text: Err(JsonEmitError::LoneSurrogate),
        },
        DumpsTestCase {
            description: "orjson refuses lone surrogates",
            value: lone_surrogate_text(),
            dialect: JsonDialect::Orjson(OrjsonOptions::default()),
            expected_text: Err(JsonEmitError::LoneSurrogate),
        },
        DumpsTestCase {
            description: "nesting within the limit is written",
            value: nested_arrays(3),
            dialect: JsonDialect::Orjson(OrjsonOptions::default()),
            expected_text: Ok("[[[]]]"),
        },
    ];
    for test_case in test_cases {
        let actual = dumps(&test_case.value, &test_case.dialect);
        assert_eq!(
            actual.as_deref().map_err(|error| *error),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_floats_when_formatting_python_repr_then_text_matches_cpython() {
    let test_cases = [
        FloatReprTestCase {
            description: "0.0",
            value: 0.0,
            expected_repr: "0.0",
        },
        FloatReprTestCase {
            description: "-0.0",
            value: -0.0,
            expected_repr: "-0.0",
        },
        FloatReprTestCase {
            description: "0.0001",
            value: 1e-4,
            expected_repr: "0.0001",
        },
        FloatReprTestCase {
            description: "1e-05",
            value: 1e-5,
            expected_repr: "1e-05",
        },
        FloatReprTestCase {
            description: "1.5e-300",
            value: 1.5e-300,
            expected_repr: "1.5e-300",
        },
        FloatReprTestCase {
            description: "5e-324",
            value: 5e-324,
            expected_repr: "5e-324",
        },
        FloatReprTestCase {
            description: "1.2345678901234568e+17",
            value: 123_456_789_012_345_680.0,
            expected_repr: "1.2345678901234568e+17",
        },
        FloatReprTestCase {
            description: "9007199254740992.0",
            value: 9_007_199_254_740_993.0,
            expected_repr: "9007199254740992.0",
        },
        FloatReprTestCase {
            description: "1.7976931348623157e+308",
            value: f64::MAX,
            expected_repr: "1.7976931348623157e+308",
        },
        FloatReprTestCase {
            description: "0.30000000000000004",
            value: 0.30000000000000004,
            expected_repr: "0.30000000000000004",
        },
        FloatReprTestCase {
            description: "nan",
            value: f64::NAN,
            expected_repr: "nan",
        },
        FloatReprTestCase {
            description: "exact halfway digit rounds half to even",
            value: 73_720_622_874_222.62,
            expected_repr: "73720622874222.62",
        },
        FloatReprTestCase {
            description: "-inf",
            value: f64::NEG_INFINITY,
            expected_repr: "-inf",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            python_repr(test_case.value),
            test_case.expected_repr,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_python_integer_text_when_parsing_then_text_is_canonical() {
    let test_cases = [
        IntegerParseTestCase {
            description: "leading zeros are dropped",
            text: "007",
            expected_decimal: Some("7"),
        },
        IntegerParseTestCase {
            description: "negative zero is zero",
            text: "-0",
            expected_decimal: Some("0"),
        },
        IntegerParseTestCase {
            description: "plus sign is dropped",
            text: "+42",
            expected_decimal: Some("42"),
        },
        IntegerParseTestCase {
            description: "negative keeps its sign",
            text: "-000123",
            expected_decimal: Some("-123"),
        },
        IntegerParseTestCase {
            description: "letters are rejected",
            text: "x",
            expected_decimal: None,
        },
        IntegerParseTestCase {
            description: "empty text is rejected",
            text: "",
            expected_decimal: None,
        },
        IntegerParseTestCase {
            description: "bare sign is rejected",
            text: "-",
            expected_decimal: None,
        },
    ];
    for test_case in test_cases {
        let parsed = JsonInteger::parse(test_case.text);
        assert_eq!(
            parsed.as_ref().map(JsonInteger::as_str),
            test_case.expected_decimal,
            "{}",
            test_case.description
        );
    }
}
