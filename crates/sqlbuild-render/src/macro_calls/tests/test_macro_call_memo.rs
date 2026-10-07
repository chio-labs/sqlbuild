use crate::macro_calls::tests::helpers::recorded_memo;
use crate::macro_calls::tests::test_types::MacroCallMemoTestCase;

#[test]
fn given_recorded_call_when_looking_up_then_only_same_class_and_text_hit() {
    let test_cases = [
        MacroCallMemoTestCase {
            description: "same class and call text",
            class_id: 1,
            call_text: "@cents(amount)",
            expected_hit: true,
        },
        MacroCallMemoTestCase {
            description: "another call class",
            class_id: 2,
            call_text: "@cents(amount)",
            expected_hit: false,
        },
        MacroCallMemoTestCase {
            description: "another call text",
            class_id: 1,
            call_text: "@cents(total)",
            expected_hit: false,
        },
    ];

    for test_case in test_cases {
        let (mut memo, entry) = recorded_memo();
        let found = memo.lookup(test_case.class_id, test_case.call_text);
        assert_eq!(
            found.as_deref() == Some(&entry),
            test_case.expected_hit,
            "{}",
            test_case.description
        );
        assert_eq!(
            memo.stats(),
            (
                usize::from(test_case.expected_hit),
                usize::from(!test_case.expected_hit),
                1
            ),
            "{}",
            test_case.description
        );
    }
}
