use crate::seeds::main::pair_seed_declarations::pair_seed_declarations;
use crate::seeds::tests::test_types::SeedPairingTestCase;

#[test]
fn given_seed_declarations_when_pairing_then_python_pairs_are_returned() {
    let test_cases = [
        SeedPairingTestCase {
            description: "declarations pair with files by stem in declaration order",
            declarations: &["products", "orders"],
            stems: &["orders", "products", "customers"],
            expected_pairs: Ok(vec![1, 0]),
        },
        SeedPairingTestCase {
            description: "a later file with the same stem wins",
            declarations: &["orders"],
            stems: &["orders", "orders"],
            expected_pairs: Ok(vec![1]),
        },
        SeedPairingTestCase {
            description: "the first declaration without a file is reported",
            declarations: &["orders", "missing", "absent"],
            stems: &["orders"],
            expected_pairs: Err(1),
        },
    ];

    for test_case in test_cases {
        let declarations: Vec<String> = test_case
            .declarations
            .iter()
            .map(|name| (*name).to_owned())
            .collect();
        let stems: Vec<String> = test_case
            .stems
            .iter()
            .map(|stem| (*stem).to_owned())
            .collect();
        assert_eq!(
            pair_seed_declarations(&declarations, &stems),
            test_case.expected_pairs,
            "{}",
            test_case.description
        );
    }
}
