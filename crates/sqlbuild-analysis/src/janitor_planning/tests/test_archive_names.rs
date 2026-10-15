//! Archive names follow the strict grammar and fit identifier limits.

use crate::janitor_planning::main::build_archive_name::build_archive_name;
use crate::janitor_planning::main::parse_archive_name::parse_archive_name;
use crate::janitor_planning::main::query_diff_artifact_name::query_diff_artifact_name;
use crate::janitor_planning::main::query_diff_artifact_parts::query_diff_artifact_parts;
use crate::janitor_planning::models::ArchiveTimestamp;
use crate::janitor_planning::tests::test_types::{
    ArtifactNameBuildTestCase, ArtifactNameTestCase, BuildArchiveNameTestCase,
    ParseArchiveNameTestCase,
};

const ARCHIVED_AT: ArchiveTimestamp = ArchiveTimestamp {
    year: 2026,
    month: 1,
    day: 15,
    hour: 12,
    minute: 30,
    second: 5,
};

#[test]
fn given_relation_name_when_parsing_archive_name_then_returns_strict_parts() {
    let test_cases = [
        ParseArchiveNameTestCase {
            description: "lowercase archive name",
            name: "_sqb_archive__20260115t123005z__orders",
            expected_parts: Some((ARCHIVED_AT, "orders")),
        },
        ParseArchiveNameTestCase {
            description: "uppercase archive name keeps logical spelling",
            name: "_SQB_ARCHIVE__20260115T123005Z__Orders__v2",
            expected_parts: Some((ARCHIVED_AT, "Orders__v2")),
        },
        ParseArchiveNameTestCase {
            description: "impossible calendar day",
            name: "_sqb_archive__20260230t000000z__orders",
            expected_parts: None,
        },
        ParseArchiveNameTestCase {
            description: "leap second",
            name: "_sqb_archive__20260115t000060z__orders",
            expected_parts: None,
        },
        ParseArchiveNameTestCase {
            description: "impossible month",
            name: "_SQB_ARCHIVE__20261324T101500Z__orders",
            expected_parts: None,
        },
        ParseArchiveNameTestCase {
            description: "missing timezone marker",
            name: "_SQB_ARCHIVE__20260924T101500__orders",
            expected_parts: None,
        },
        ParseArchiveNameTestCase {
            description: "ordinary relation",
            name: "orders_archive",
            expected_parts: None,
        },
        ParseArchiveNameTestCase {
            description: "single separator",
            name: "_sqb_archive_20260115t000000z__orders",
            expected_parts: None,
        },
        ParseArchiveNameTestCase {
            description: "missing logical name",
            name: "_sqb_archive__20260115t000000z__",
            expected_parts: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            parse_archive_name(test_case.name)
                .map(|parsed| (parsed.archived_at, parsed.logical_name)),
            test_case
                .expected_parts
                .map(|(archived_at, logical)| (archived_at, logical.to_owned())),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_original_name_when_building_archive_name_then_fits_and_folds() {
    let test_cases = [
        BuildArchiveNameTestCase {
            description: "short name is kept and folded",
            original_name: "Orders",
            identifier_limit: 255,
            kind: None,
            expected_name: Ok("_sqb_archive__20260115t123005z__orders"),
        },
        BuildArchiveNameTestCase {
            description: "kind segment follows the timestamp",
            original_name: "orders",
            identifier_limit: 255,
            kind: Some("migrated"),
            expected_name: Ok("_sqb_archive__20260115t123005z__migrated__orders"),
        },
        BuildArchiveNameTestCase {
            description: "prefix exceeding the limit fails",
            original_name: "orders",
            identifier_limit: 10,
            kind: None,
            expected_name: Err(
                "Janitor archive prefix '_SQB_ARCHIVE__20260115T123005Z__' does not fit within identifier limit 10",
            ),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            build_archive_name(
                (test_case.original_name, ARCHIVED_AT),
                test_case.identifier_limit,
                test_case.kind,
            ),
            test_case
                .expected_name
                .map(str::to_owned)
                .map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_relation_name_when_checking_query_diff_artifact_then_returns_run_and_side() {
    let test_cases = [
        ArtifactNameTestCase {
            description: "strict artifact name",
            name: "__sqlbuild_query_diff_20260115T123005Z_0123456789ab_LEFT",
            expected_parts: Some(("20260115T123005Z_0123456789ab", "left")),
        },
        ArtifactNameTestCase {
            description: "short run suffix",
            name: "__sqlbuild_query_diff_20260115T123005Z_0123_left",
            expected_parts: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            query_diff_artifact_parts(test_case.name),
            test_case
                .expected_parts
                .map(|(run_id, side)| (run_id.to_owned(), side.to_owned())),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_run_and_side_when_building_query_diff_artifact_name_then_parses_back() {
    let test_cases = [
        ArtifactNameBuildTestCase {
            description: "generated run id round trips",
            run_id: "20260115T123005Z_0123456789ab",
            side: "right",
            expected_parts: Some(("20260115T123005Z_0123456789ab", "right")),
        },
        ArtifactNameBuildTestCase {
            description: "free-form run id is not reserved",
            run_id: "manual",
            side: "left",
            expected_parts: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            query_diff_artifact_parts(&query_diff_artifact_name(test_case.run_id, test_case.side)),
            test_case
                .expected_parts
                .map(|(run_id, side)| (run_id.to_owned(), side.to_owned())),
            "{}",
            test_case.description
        );
    }
}
