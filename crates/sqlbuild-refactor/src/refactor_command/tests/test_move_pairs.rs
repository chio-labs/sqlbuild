use crate::refactor_command::main::move_pairs::move_pairs;
use crate::refactor_command::models::MoveArguments;
use crate::refactor_command::tests::test_types::MovePairsTestCase;

#[test]
fn given_words_and_move_file_when_reading_pairs_then_every_pair_is_read_in_order() {
    let test_cases = [
        MovePairsTestCase {
            description: "pairs on the command line, then from the file",
            words: &["orders", "models/finance/", "customers", "models/crm/"],
            file: Some("# moves\n\nrefunds\tmodels/finance/\n  totals   models/marts/t.sql  \n"),
            expected_pairs: Ok(&[
                ("orders", "models/finance/"),
                ("customers", "models/crm/"),
                ("refunds", "models/finance/"),
                ("totals", "models/marts/t.sql"),
            ]),
        },
        MovePairsTestCase {
            description: "a target without a destination",
            words: &["orders", "models/finance/", "customers"],
            file: None,
            expected_pairs: Err("'customers' has no DESTINATION"),
        },
        MovePairsTestCase {
            description: "a file line with three words",
            words: &[],
            file: Some("orders models/finance/ extra\n"),
            expected_pairs: Err(
                "moves.tsv:1: expected TARGET and DESTINATION separated by a tab or spaces, \
                 found 3 words",
            ),
        },
        MovePairsTestCase {
            description: "nothing to move",
            words: &[],
            file: Some("# only a comment\n"),
            expected_pairs: Err("sqb mv needs a TARGET and a DESTINATION"),
        },
    ];
    for test_case in test_cases {
        let pairs = move_pairs(&MoveArguments {
            words: test_case.words.to_vec(),
            file: test_case.file.map(|contents| ("moves.tsv", contents)),
        });

        assert_eq!(
            pairs.map_err(|error| error.message),
            test_case
                .expected_pairs
                .map(|pairs| {
                    pairs
                        .iter()
                        .map(|(target, destination)| {
                            ((*target).to_owned(), (*destination).to_owned())
                        })
                        .collect::<Vec<_>>()
                })
                .map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
