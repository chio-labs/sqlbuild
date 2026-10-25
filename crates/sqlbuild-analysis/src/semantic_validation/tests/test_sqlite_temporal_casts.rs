use crate::semantic_validation::_helpers::sqlite_temporal_casts::{
    TemporalCast, sqlite_temporal_cast_warnings, temporal_casts,
};
use crate::semantic_validation::tests::test_types::{
    TemporalCastDialectTestCase, TemporalCastScanTestCase,
};
use polyglot_sql::DialectType;

#[test]
fn given_authored_sql_when_scanning_temporal_casts_then_finds_only_cast_types() {
    let test_cases = [
        TemporalCastScanTestCase {
            description: "timestamp and date casts are found in any case",
            sql: "SELECT CAST(a AS TIMESTAMP), cast(b as date), CAST(c AS TEXT) FROM t",
            expected_casts: &[(7, 26, "TIMESTAMP"), (29, 43, "DATE")],
        },
        TemporalCastScanTestCase {
            description: "a nested cast's type is not the outer cast's",
            sql: "SELECT CAST(COALESCE(a, CAST(1 AS TEXT)) AS DATETIME) FROM t",
            expected_casts: &[(7, 52, "DATETIME")],
        },
        TemporalCastScanTestCase {
            description: "aliases, quoted text and comments are ignored",
            sql: "SELECT (SELECT 1 AS date) AS d, 'CAST(x AS DATE)' -- CAST(y AS DATE)\nFROM t",
            expected_casts: &[],
        },
    ];
    for test_case in test_cases {
        let found: Vec<TemporalCast> = temporal_casts(test_case.sql);
        let spans: Vec<(usize, usize, &str)> = found
            .iter()
            .map(|cast| (cast.start, cast.end, cast.type_name.as_str()))
            .collect();
        assert_eq!(spans, test_case.expected_casts, "{}", test_case.description);
    }
}

#[test]
fn given_dialect_when_checking_temporal_casts_then_only_sqlite_warns() {
    let test_cases = [
        TemporalCastDialectTestCase {
            description: "SQLite warns about a timestamp cast",
            dialect: DialectType::SQLite,
            expected_warnings: 1,
        },
        TemporalCastDialectTestCase {
            description: "DuckDB casts timestamps natively",
            dialect: DialectType::DuckDB,
            expected_warnings: 0,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            sqlite_temporal_cast_warnings("SELECT CAST(a AS TIMESTAMP) FROM t", test_case.dialect)
                .len(),
            test_case.expected_warnings,
            "{}",
            test_case.description
        );
    }
}
