use crate::definition_locations::main::decorator_location::decorator_location;
use crate::definition_locations::tests::test_types::DecoratorLocationTestCase;

/// Expectations recorded from the CPython `ast` implementation this replaces.
#[test]
fn given_module_when_locating_udf_decorator_then_matches_cpython_position() {
    let test_cases = [
        DecoratorLocationTestCase {
            description: "a call decorator",
            contents: "import sqlbuild\n\n\n@sqlbuild.udf(returns=\"INTEGER\")\ndef add_one(value):\n    return value + 1\n",
            python_version: (3, 12),
            expected_location: (4, 1),
        },
        DecoratorLocationTestCase {
            description: "a bare decorator in a class, found breadth first",
            contents: "class Box:\n    @udf\n    def method(self):\n        pass\n\n@ udf\ndef top():\n    pass\n",
            python_version: (3, 12),
            expected_location: (6, 2),
        },
        DecoratorLocationTestCase {
            description: "columns count UTF-8 bytes",
            contents: "x = \"é\"; y = 1\nif x:\n\t@é.udf()\n\tdef f():\n\t\tpass\n",
            python_version: (3, 12),
            expected_location: (3, 2),
        },
        DecoratorLocationTestCase {
            description: "carriage returns end lines",
            contents: "x = 1\r@udf\rdef f():\r    pass\r",
            python_version: (3, 12),
            expected_location: (2, 1),
        },
        DecoratorLocationTestCase {
            description: "a parenthesized decorator starts at its parenthesis",
            contents: "@(udf)(a=1)\ndef f():\n    pass\n",
            python_version: (3, 12),
            expected_location: (1, 1),
        },
        DecoratorLocationTestCase {
            description: "a missing decorator",
            contents: "@other\ndef f():\n    pass\n",
            python_version: (3, 12),
            expected_location: (1, 1),
        },
        DecoratorLocationTestCase {
            description: "a syntax error",
            contents: "x = 1\n@udf\ndef f(:\n",
            python_version: (3, 12),
            expected_location: (1, 1),
        },
        DecoratorLocationTestCase {
            description: "syntax newer than the interpreter is a syntax error",
            contents: "x = t\"tpl\"\n@udf\ndef f():\n    pass\n",
            python_version: (3, 13),
            expected_location: (1, 1),
        },
        DecoratorLocationTestCase {
            description: "syntax the interpreter supports",
            contents: "x = t\"tpl\"\n@udf\ndef f():\n    pass\n",
            python_version: (3, 14),
            expected_location: (2, 1),
        },
        DecoratorLocationTestCase {
            description: "a leading byte order mark is not printable source",
            contents: "\u{feff}@udf\ndef f():\n    pass\n",
            python_version: (3, 12),
            expected_location: (1, 1),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            decorator_location(test_case.contents, "udf", test_case.python_version),
            test_case.expected_location,
            "{}",
            test_case.description
        );
    }
}
