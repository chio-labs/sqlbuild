use std::io;

use crate::tree::_helpers::listing::collect_listing;
use crate::tree::models::TreeEntry;
use crate::tree::tests::test_types::InterruptedListingTestCase;

/// A `readdir` failure after the directory opened empties the listing and marks it interrupted.
#[test]
fn given_injected_listing_errors_when_collecting_then_listing_is_empty_and_interrupted() {
    let test_cases = [
        InterruptedListingTestCase {
            description: "a complete listing",
            entries: &[Some("orders.sql"), Some("customers.sql")],
            expected_names: &["orders.sql", "customers.sql"],
            expected_interrupted: false,
        },
        InterruptedListingTestCase {
            description: "a failure after the first entry",
            entries: &[Some("orders.sql"), None, Some("customers.sql")],
            expected_names: &[],
            expected_interrupted: true,
        },
        InterruptedListingTestCase {
            description: "a failure before any entry",
            entries: &[None],
            expected_names: &[],
            expected_interrupted: true,
        },
    ];
    for test_case in test_cases {
        let results = test_case
            .entries
            .iter()
            .map(|entry| entry.ok_or_else(|| io::Error::other("injected readdir failure")));
        let listing = collect_listing(results, |name| TreeEntry {
            name: name.to_owned(),
            raw_name: None,
            segment: name.to_owned(),
            is_dir: false,
            is_walkable_dir: false,
        });
        let names: Vec<&str> = listing
            .entries
            .iter()
            .map(|entry| entry.name.as_str())
            .collect();
        assert_eq!(names, test_case.expected_names, "{}", test_case.description);
        assert_eq!(
            listing.interrupted, test_case.expected_interrupted,
            "{}",
            test_case.description
        );
    }
}
