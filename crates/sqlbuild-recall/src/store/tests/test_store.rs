use crate::records::main::invocation_row::invocation_row;
use crate::records::models::{InvocationContext, OutputStream, RecallValue};
use crate::store::_helpers::truncation::truncation_note;
use crate::store::errors::StoreErrorKind;
use crate::store::main::describe_store::describe_store;
use crate::store::main::query_store::query_store;
use crate::store::main::read_output_transcript::read_output_transcript;
use crate::store::main::resolve_invocation::resolve_invocation;
use crate::store::tests::helpers::{
    NOW, chunk, envelope, error_kind, new_store, newer_schema_store, rows, shifted, write,
};
#[cfg(unix)]
use crate::store::tests::helpers::{
    already_replaced, lock_held, nobody_else, open_under_locked_directory, quarantine_after,
};
#[cfg(unix)]
use crate::store::tests::test_types::{LockedDirectoryTestCase, QuarantineTestCase};
use crate::store::tests::test_types::{
    NewerSchemaTestCase, QueryTestCase, ResolveInvocationTestCase, TranscriptTestCase,
    TruncationNoteTestCase,
};

#[test]
fn given_ids_when_resolved_then_prefixes_last_and_ambiguity_are_exact() {
    let (_directory, store) = new_store();
    write(
        &store,
        &[
            invocation_row(
                &envelope("abc123", &shifted(-20)),
                &InvocationContext::default(),
            ),
            invocation_row(
                &envelope("abd456", &shifted(-10)),
                &InvocationContext::default(),
            ),
        ],
    );
    let test_cases = [
        ResolveInvocationTestCase {
            description: "a unique prefix resolves",
            selector: "abc",
            expected_invocation: Ok("abc123"),
        },
        ResolveInvocationTestCase {
            description: "last is the most recently started invocation",
            selector: "last",
            expected_invocation: Ok("abd456"),
        },
        ResolveInvocationTestCase {
            description: "a shared prefix is ambiguous",
            selector: "ab",
            expected_invocation: Err(StoreErrorKind::Ambiguous),
        },
        ResolveInvocationTestCase {
            description: "an unknown prefix is not found",
            selector: "zz",
            expected_invocation: Err(StoreErrorKind::NotFound),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            error_kind(resolve_invocation(&store, test_case.selector)),
            test_case.expected_invocation.map(str::to_owned),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_queries_when_run_then_writes_are_rejected_and_truncation_reported() {
    let (_directory, store) = new_store();
    let env = envelope("q", NOW);
    for sequence in 0..3 {
        write(
            &store,
            &[chunk(&env, (sequence, OutputStream::Stdout, b"line\n"))],
        );
    }
    let test_cases = [
        QueryTestCase {
            description: "a limit truncates and is reported",
            sql: "SELECT sequence FROM recall_output ORDER BY sequence",
            limit: Some(2),
            expected_shape: Ok((vec!["sequence".to_owned()], 2, true)),
        },
        QueryTestCase {
            description: "without a limit every row returns",
            sql: "SELECT sequence FROM recall_output ORDER BY sequence",
            limit: None,
            expected_shape: Ok((vec!["sequence".to_owned()], 3, false)),
        },
        QueryTestCase {
            description: "writes are rejected",
            sql: "DELETE FROM recall_output",
            limit: None,
            expected_shape: Err(StoreErrorKind::Query),
        },
        QueryTestCase {
            description: "invalid SQL is a query error",
            sql: "SELEC nope",
            limit: None,
            expected_shape: Err(StoreErrorKind::Query),
        },
    ];

    for test_case in test_cases {
        let shape = error_kind(query_store(&store, test_case.sql, test_case.limit))
            .map(|result| (result.columns, result.rows.len(), result.truncated));
        assert_eq!(shape, test_case.expected_shape, "{}", test_case.description);
    }
}

#[test]
fn given_output_without_delivery_facts_when_read_then_bytes_return_and_completeness_is_unproven() {
    let (_directory, store) = new_store();
    let env = envelope("q", NOW);
    for sequence in 0..3 {
        write(
            &store,
            &[chunk(&env, (sequence, OutputStream::Stdout, b"line\n"))],
        );
    }
    let test_cases = [TranscriptTestCase {
        description: "chunks concatenate in sequence order",
        invocation_id: "q",
        expected_transcript: Ok((b"line\nline\nline\n".to_vec(), false)),
    }];

    for test_case in test_cases {
        let transcript = error_kind(read_output_transcript(
            &store,
            test_case.invocation_id,
            None,
        ))
        .map(|transcript| (transcript.data, transcript.complete));
        assert_eq!(
            transcript, test_case.expected_transcript,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_newer_schema_version_when_ensured_then_views_are_kept_and_read_only_opens_work() {
    let (_directory, store) = newer_schema_store();
    let relations = describe_store(&store).expect("the store can be described");
    let data_nullable: Option<bool> = relations
        .iter()
        .find(|relation| relation.name == "recall_output")
        .and_then(|relation| relation.columns.iter().find(|column| column.name == "data"))
        .map(|column| column.nullable);
    let test_cases = [
        NewerSchemaTestCase {
            description: "a newer view definition is not replaced",
            sql: "SELECT marker FROM conflicts",
            expected_rows: vec![vec![RecallValue::Text("newer".to_owned())]],
            expected_first_kind: "view",
            expected_data_nullable: Some(false),
        },
        NewerSchemaTestCase {
            description: "the read-only store answers view queries",
            sql: "SELECT COUNT(*) FROM invocations",
            expected_rows: vec![vec![RecallValue::Integer(0)]],
            expected_first_kind: "view",
            expected_data_nullable: Some(false),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            (
                rows(&store, test_case.sql),
                relations[0].kind.as_str(),
                data_nullable
            ),
            (
                test_case.expected_rows,
                test_case.expected_first_kind,
                test_case.expected_data_nullable
            ),
            "{}",
            test_case.description
        );
    }
}

#[cfg(unix)]
#[test]
fn given_a_read_only_directory_when_opened_then_the_error_is_a_permission_failure() {
    let test_cases = [
        LockedDirectoryTestCase {
            description: "a missing logs directory cannot be created",
            relative_path: "logs/recall.sqlite3",
            expected_kind: Err(StoreErrorKind::Permission),
        },
        LockedDirectoryTestCase {
            description: "the database file cannot be created",
            relative_path: "recall.sqlite3",
            expected_kind: Err(StoreErrorKind::Permission),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            open_under_locked_directory(test_case.relative_path),
            test_case.expected_kind,
            "{}",
            test_case.description
        );
    }
}

#[cfg(unix)]
#[test]
fn given_a_stale_observation_when_quarantining_then_only_the_observed_file_is_moved() {
    let test_cases = [
        QuarantineTestCase {
            description: "the observed corrupt file is moved aside",
            race: nobody_else,
            expected_outcome: (true, 1, false),
        },
        QuarantineTestCase {
            description: "a store another process already replaced is kept",
            race: already_replaced,
            expected_outcome: (false, 1, true),
        },
        QuarantineTestCase {
            description: "a held quarantine lock moves nothing",
            race: lock_held,
            expected_outcome: (false, 0, false),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            quarantine_after(test_case.race),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_truncated_output_when_noted_then_sizes_read_naturally() {
    let test_cases = [
        TruncationNoteTestCase {
            description: "the default limit keeps equal halves",
            omitted: 23_600_000,
            kept: (1_048_576, 1_048_576),
            expected_note: "\u{2026} 23.6 MB of stdout not recorded (kept the first and last \
                            1 MiB). Raise [recall] max_output_bytes to keep more.\n",
        },
        TruncationNoteTestCase {
            description: "an odd limit keeps one more byte at the start",
            omitted: 999,
            kept: (3, 2),
            expected_note: "\u{2026} 999 bytes of stdout not recorded (kept the first 3 bytes \
                            and the last 2 bytes). Raise [recall] max_output_bytes to keep more.\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            truncation_note("stdout", test_case.omitted, test_case.kept),
            test_case.expected_note,
            "{}",
            test_case.description
        );
    }
}
