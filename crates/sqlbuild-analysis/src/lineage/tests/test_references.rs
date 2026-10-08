use crate::lineage::_helpers::references::{normalized_sql, physical_resources};
use crate::lineage::tests::test_types::ReferenceTestCase;

#[test]
fn given_reference_calls_when_normalizing_then_matches_python_patterns() {
    let test_cases = [
        ReferenceTestCase {
            description: "each resource kind, spaced quotes and an underscore run",
            sql: "SELECT * FROM __ref('orders') JOIN __source( \"raw.events\" ) ON 1=1 \
                  JOIN ___seed('regions')",
            expected_resources: &[
                ("model", "orders", "__sqlbuild_model__orders"),
                ("source", "raw.events", "__sqlbuild_source__raw__events"),
                ("seed", "regions", "__sqlbuild_seed__regions"),
            ],
            expected_normalized: "SELECT * FROM __sqlbuild_model__orders JOIN \
                                  __sqlbuild_source__raw__events ON 1=1 JOIN ___sqlbuild_seed__regions",
        },
        ReferenceTestCase {
            description: "a UDF call, mismatched and empty quotes, and a non-ASCII name",
            sql: "SELECT __udf('my.fn') (x), __ref('a\") , __ref(''), __ref( '\u{e9} b' )\t)",
            expected_resources: &[("model", "\u{e9} b", "__sqlbuild_model______b")],
            expected_normalized: "SELECT my__fn(x), __ref('a\") , __ref(''), __sqlbuild_model______b\t)",
        },
        ReferenceTestCase {
            description: "Python whitespace beyond ASCII and an unknown call",
            sql: "SELECT __ref('orders'\u{1c}) FROM x __unknown('a') __ref(\"q\")",
            expected_resources: &[
                ("model", "orders", "__sqlbuild_model__orders"),
                ("model", "q", "__sqlbuild_model__q"),
            ],
            expected_normalized: "SELECT __sqlbuild_model__orders FROM x __unknown('a') __sqlbuild_model__q",
        },
    ];
    for test_case in test_cases {
        let resources: Vec<(&str, String, String)> = physical_resources(test_case.sql)
            .into_iter()
            .map(|resource| {
                (
                    resource.resource_type.as_str(),
                    resource.resource_name,
                    resource.physical_name,
                )
            })
            .collect();
        let expected: Vec<(&str, String, String)> = test_case
            .expected_resources
            .iter()
            .map(|(kind, name, physical)| (*kind, (*name).to_owned(), (*physical).to_owned()))
            .collect();
        assert_eq!(resources, expected, "{}", test_case.description);
        assert_eq!(
            normalized_sql(test_case.sql),
            test_case.expected_normalized,
            "{}",
            test_case.description
        );
    }
}
