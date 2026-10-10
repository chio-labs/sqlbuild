use crate::lineage::_helpers::authored_files::AuthoredFiles;
use crate::lineage::_helpers::fingerprint_digest::fingerprint_outcome;
use crate::lineage::models::InterruptedListingPolicy;
use crate::lineage::tests::helpers::fingerprint_status;
use crate::lineage::tests::test_types::{
    InterruptedListingPolicyTestCase, UnavailableWalkTestCase,
};
use sqlbuild_discovery::models::{ReadFailure, StageFailure};

/// A listing interrupted after its directory opened is uncacheable on 3.12 and skipped later.
#[test]
fn given_interrupted_listings_when_fingerprinting_then_policy_decides_cacheability() {
    let test_cases = [
        InterruptedListingPolicyTestCase {
            description: "Python 3.12 escapes the error from Path.walk",
            interrupted: true,
            policy: InterruptedListingPolicy::Uncacheable,
            expected_status: "uncacheable",
        },
        InterruptedListingPolicyTestCase {
            description: "Python 3.13 and later skip the directory",
            interrupted: true,
            policy: InterruptedListingPolicy::Skip,
            expected_status: "digest",
        },
        InterruptedListingPolicyTestCase {
            description: "no interruption under the 3.12 policy",
            interrupted: false,
            policy: InterruptedListingPolicy::Uncacheable,
            expected_status: "digest",
        },
    ];
    for test_case in test_cases {
        let authored = AuthoredFiles::Files {
            files: Vec::new(),
            interrupted: test_case.interrupted,
        };
        let status = fingerprint_status(fingerprint_outcome(authored, b"prefix", test_case.policy));
        assert_eq!(
            status, test_case.expected_status,
            "{}",
            test_case.description
        );
    }
}

/// An unlistable root is Python's `OSError` (`None`); an internal walk failure is an error.
#[test]
fn given_an_unavailable_walk_when_fingerprinting_then_only_internal_failures_fail() {
    let test_cases = [
        UnavailableWalkTestCase {
            description: "an unlistable directory is uncacheable",
            failure: || StageFailure::Unlistable {
                relative_path: String::new(),
                error: ReadFailure::Io {
                    errno: Some(13),
                    winerror: None,
                    message: "Permission denied".to_owned(),
                },
            },
            expected_status: "uncacheable",
        },
        UnavailableWalkTestCase {
            description: "a walk that could not start fails",
            failure: || StageFailure::Internal("pool".to_owned()),
            expected_status: "failed: pool",
        },
    ];
    for test_case in test_cases {
        let authored = AuthoredFiles::Unavailable((test_case.failure)());
        let status = fingerprint_status(fingerprint_outcome(
            authored,
            b"prefix",
            InterruptedListingPolicy::Skip,
        ));
        assert_eq!(
            status, test_case.expected_status,
            "{}",
            test_case.description
        );
    }
}
