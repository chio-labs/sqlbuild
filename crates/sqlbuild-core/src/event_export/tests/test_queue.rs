use crate::event_export::main::queue_lifecycle_event::queue_lifecycle_event;
use crate::event_export::main::take_lifecycle_event::take_lifecycle_event;
use crate::event_export::models::EventQueue;
use crate::event_export::tests::helpers::queued;
use crate::event_export::tests::test_types::{DeliveryOrderTestCase, DisplacementTestCase};

#[test]
fn given_full_queue_when_priority_pair_arrives_then_displacement_policy_is_exact() {
    let test_cases = [
        DisplacementTestCase {
            description: "equal priority is rejected",
            priorities: (2, 2),
            expected_inserted: false,
            expected_displaced: None,
            expected_retained: 1,
        },
        DisplacementTestCase {
            description: "lower priority is rejected",
            priorities: (3, 0),
            expected_inserted: false,
            expected_displaced: None,
            expected_retained: 1,
        },
        DisplacementTestCase {
            description: "higher priority displaces the queued event",
            priorities: (0, 1),
            expected_inserted: true,
            expected_displaced: Some(1),
            expected_retained: 2,
        },
    ];

    for test_case in test_cases {
        let (queued_priority, incoming_priority) = test_case.priorities;
        let first = queue_lifecycle_event(EventQueue::new(1), queued(1, (queued_priority, false)));
        let outcome = queue_lifecycle_event(first.queue, queued(2, (incoming_priority, false)));
        let (_, retained) = take_lifecycle_event(outcome.queue);
        let retained = retained.map(|event| event.sequence);
        assert!(first.inserted, "{}", test_case.description);
        assert_eq!(
            (
                outcome.inserted,
                outcome.displaced.map(|event| event.sequence),
                retained
            ),
            (
                test_case.expected_inserted,
                test_case.expected_displaced,
                Some(test_case.expected_retained)
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_queued_events_when_taking_then_priority_then_fifo_with_invocation_terminals_last() {
    let test_cases = [
        DeliveryOrderTestCase {
            description: "highest priority first and FIFO within a priority",
            events: &[(0, false), (3, false), (2, false), (3, false), (0, false)],
            expected_sequences: &[1, 3, 2, 0, 4],
        },
        DeliveryOrderTestCase {
            description: "invocation terminals wait behind lower-priority events",
            events: &[(3, true), (0, false), (1, false)],
            expected_sequences: &[2, 1, 0],
        },
    ];

    for test_case in test_cases {
        let mut queue: EventQueue<()> = EventQueue::new(16);
        for (sequence, event) in (0_u64..).zip(test_case.events) {
            queue = queue_lifecycle_event(queue, queued(sequence, *event)).queue;
        }
        let mut order: Vec<u64> = Vec::new();
        for _ in test_case.events {
            let (rest, next) = take_lifecycle_event(queue);
            queue = rest;
            order.extend(next.map(|event| event.sequence));
        }
        assert_eq!(
            order, test_case.expected_sequences,
            "{}",
            test_case.description
        );
    }
}
