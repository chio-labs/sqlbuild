use crate::records::main::invocation_row::invocation_row;
use crate::records::main::meta_row::meta_row;
use crate::records::models::{InvocationContext, OutputStream, RecallValue};
use crate::store::errors::StoreErrorKind;
use crate::store::main::describe_store::describe_store;
use crate::store::main::ensure_sqlite_schema::ensure_sqlite_schema;
use crate::store::main::open_sqlite_store::open_sqlite_store;
use crate::store::main::query_store::query_store;
use crate::store::main::read_output_transcript::read_output_transcript;
use crate::store::main::resolve_invocation::resolve_invocation;
use crate::store::models::OpenMode;
use crate::store::tests::helpers::{NOW, chunk, envelope, new_store, rows, shifted, write};

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
    assert_eq!(resolve_invocation(&store, "abc").as_deref(), Ok("abc123"));
    assert_eq!(resolve_invocation(&store, "last").as_deref(), Ok("abd456"));
    assert_eq!(
        resolve_invocation(&store, "ab").map_err(|error| error.kind),
        Err(StoreErrorKind::Ambiguous)
    );
    assert_eq!(
        resolve_invocation(&store, "zz").map_err(|error| error.kind),
        Err(StoreErrorKind::NotFound)
    );
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
    let limited = query_store(
        &store,
        "SELECT sequence FROM recall_output ORDER BY sequence",
        Some(2),
    )
    .expect("query");
    assert_eq!(limited.rows.len(), 2);
    assert!(limited.truncated);
    assert_eq!(limited.columns, vec!["sequence".to_owned()]);
    let rejected =
        query_store(&store, "DELETE FROM recall_output", None).expect_err("write rejected");
    assert_eq!(rejected.kind, StoreErrorKind::Query);
    let invalid = query_store(&store, "SELEC nope", None).expect_err("invalid sql");
    assert_eq!(invalid.kind, StoreErrorKind::Query);
    let transcript = read_output_transcript(&store, "q", None).expect("transcript");
    assert_eq!(transcript.data, b"line\nline\nline\n".to_vec());
    assert!(!transcript.complete);
}

#[test]
fn given_a_newer_schema_version_when_ensured_then_views_are_kept() {
    let (directory, store) = new_store();
    write(
        &store,
        &[meta_row(
            &envelope("newer", NOW),
            ("schema", "schema_version", "99"),
            NOW,
        )],
    );
    store
        .connection
        .execute_batch("DROP VIEW conflicts; CREATE VIEW conflicts AS SELECT 'newer' AS marker")
        .expect("newer view");
    drop(store);
    let path = directory.path().join("logs/recall.sqlite3");
    let reopened = open_sqlite_store(&path, OpenMode::ReadWrite).expect("reopen");
    ensure_sqlite_schema(&reopened, &envelope("older", NOW), NOW).expect("ensure");
    assert_eq!(
        rows(&reopened, "SELECT marker FROM conflicts"),
        vec![vec![RecallValue::Text("newer".to_owned())]]
    );
    let relations = describe_store(&reopened).expect("describe");
    assert_eq!(relations[0].kind, "view");
    assert!(relations.iter().any(|relation| {
        relation.name == "recall_output"
            && relation
                .columns
                .iter()
                .any(|column| column.name == "data" && !column.nullable)
    }));
    let read_only = open_sqlite_store(&path, OpenMode::ReadOnly).expect("read-only open");
    assert!(query_store(&read_only, "SELECT * FROM invocations", None).is_ok());
}

#[cfg(unix)]
#[test]
fn given_a_read_only_directory_when_opened_then_the_error_is_a_permission_failure() {
    use std::os::unix::fs::PermissionsExt;
    let directory = tempfile::tempdir().expect("temporary directory");
    let locked = directory.path().join("locked");
    std::fs::create_dir(&locked).expect("directory");
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o555)).expect("chmod");
    let result = open_sqlite_store(&locked.join("logs/recall.sqlite3"), OpenMode::ReadWrite);
    let direct = open_sqlite_store(&locked.join("recall.sqlite3"), OpenMode::ReadWrite);
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o755)).expect("restore");
    if nix_is_root() {
        return;
    }
    assert_eq!(
        result.map(|_| ()).map_err(|error| error.kind),
        Err(StoreErrorKind::Permission)
    );
    assert_eq!(
        direct.map(|_| ()).map_err(|error| error.kind),
        Err(StoreErrorKind::Permission)
    );
}

#[cfg(unix)]
fn nix_is_root() -> bool {
    std::env::var("USER").is_ok_and(|user| user == "root")
}
