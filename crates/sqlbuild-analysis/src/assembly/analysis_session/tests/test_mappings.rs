use crate::assembly::analysis_session::_helpers::mappings::{dict_from_pairs, same_mapping};
use crate::assembly::analysis_session::_helpers::schedule::waves;
use crate::assembly::analysis_session::tests::helpers::pairs;
use crate::assembly::analysis_session::tests::test_types::{DictTestCase, WavesTestCase};

#[test]
fn given_pairs_when_building_a_dict_then_keeps_first_position_and_last_value() {
    let test_cases = [
        DictTestCase {
            description: "distinct keys keep their order",
            pairs: &[("b", "INT"), ("a", "TEXT")],
            expected_dict: &[("b", "INT"), ("a", "TEXT")],
        },
        DictTestCase {
            description: "a repeated key keeps its first position and takes the last value",
            pairs: &[("up", "INT"), ("other", "TEXT"), ("up", "BIGINT")],
            expected_dict: &[("up", "BIGINT"), ("other", "TEXT")],
        },
    ];
    for test_case in test_cases {
        let built = dict_from_pairs(pairs(test_case.pairs));

        assert_eq!(
            built,
            pairs(test_case.expected_dict),
            "{}",
            test_case.description
        );
        assert!(
            same_mapping(&built, &built.iter().rev().cloned().collect()),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_producers_when_scheduling_then_returns_topological_waves() {
    let test_cases = [
        WavesTestCase {
            description: "independent models share one wave",
            producers: &[&[], &[]],
            expected_waves: Some(&[&[0, 1]]),
        },
        WavesTestCase {
            description: "a consumer waits for every producer",
            producers: &[&[2], &[], &[1], &[0, 1]],
            expected_waves: Some(&[&[1], &[2], &[0], &[3]]),
        },
        WavesTestCase {
            description: "a cycle cannot be scheduled",
            producers: &[&[1], &[0]],
            expected_waves: None,
        },
    ];
    for test_case in test_cases {
        let producers: Vec<Vec<usize>> = test_case
            .producers
            .iter()
            .map(|producers| producers.to_vec())
            .collect();
        let scheduled: Option<Vec<Vec<usize>>> = waves(&producers);

        assert_eq!(
            format!("{scheduled:?}"),
            format!("{:?}", test_case.expected_waves),
            "{}",
            test_case.description
        );
    }
}
