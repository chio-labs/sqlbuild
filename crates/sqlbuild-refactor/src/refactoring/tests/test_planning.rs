use crate::refactoring::_helpers::planning::model_planning::decide_model_migration;
use crate::refactoring::errors::{RefactorError, RefactorErrorKind};
use crate::refactoring::models::RefactorOperation;
use crate::refactoring::tests::helpers::{
    blocking_reasons, change, commit_failure, facts, files_on_disk, model, model_in_database,
    owned_pairs, refused_target, replace_all, request, write_files,
};
use crate::refactoring::tests::test_types::{
    CollisionTestCase, CommitTestCase, MigrationDecisionTestCase, RefusedTargetTestCase,
};

#[test]
fn given_taken_name_or_destination_when_planning_then_collisions_block() -> Result<(), RefactorError>
{
    let project = tempfile::tempdir().map_err(|error| RefactorError::value(error.to_string()))?;
    write_files(project.path(), &[("models/finance/orders.sql", "SELECT 1")])?;
    let project_facts = facts(
        &project.path().to_string_lossy(),
        vec![
            model("orders", Some("table"), "analytics"),
            model("Order_Lines", Some("table"), "analytics"),
        ],
    );
    let test_cases = [
        CollisionTestCase {
            description: "a rename onto another model's name, ignoring case",
            request: request(RefactorOperation::RenameModel, "order_lines", None),
            expected_reasons: &["models/Order_Lines.sql: model:order_lines already exists"],
        },
        CollisionTestCase {
            description: "a move onto an existing file",
            request: request(RefactorOperation::MoveModel, "", Some("models/finance/")),
            expected_reasons: &["models/finance/orders.sql: destination file already exists"],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            blocking_reasons(&project_facts, &test_case.request)?,
            test_case.expected_reasons,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_destination_outside_project_when_moving_then_request_is_refused() {
    let project_facts = facts(
        "/nonexistent/project",
        vec![model("orders", Some("table"), "analytics")],
    );
    let test_cases = [RefusedTargetTestCase {
        description: "a destination above the project directory",
        request: request(
            RefactorOperation::MoveModel,
            "",
            Some("../elsewhere/orders.sql"),
        ),
        expected_error: (
            "C955",
            "destination '../elsewhere/orders.sql' is outside the project",
        ),
    }];
    for test_case in test_cases {
        assert_eq!(
            refused_target(&project_facts, &test_case.request),
            Some((
                test_case.expected_error.0.to_owned(),
                test_case.expected_error.1.to_owned()
            )),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_relation_change_when_deciding_migration_then_python_decision_is_made() {
    let before = vec![
        model("orders", Some("table"), "analytics"),
        model("customers", Some("view"), "analytics"),
    ];
    let test_cases = [
        MigrationDecisionTestCase {
            description: "a renamed table keeps its history",
            before: before.clone(),
            after: Some(vec![
                model("order_lines", Some("table"), "analytics"),
                model("customers", Some("view"), "analytics"),
            ]),
            expected_decision: (
                true,
                false,
                "keeps the relation's history and its old name working",
            ),
        },
        MigrationDecisionTestCase {
            description: "an unknown materialization keeps no data",
            before: vec![model("orders", None, "analytics")],
            after: None,
            expected_decision: (false, false, "'None' models keep no warehouse data"),
        },
        MigrationDecisionTestCase {
            description: "an edited project that does not compile still gets migrate_from",
            before: before.clone(),
            after: None,
            expected_decision: (
                true,
                false,
                "keeps the relation's history; the destination could not be checked because the edited project does not compile",
            ),
        },
        MigrationDecisionTestCase {
            description: "a move across databases is blocked",
            before: before.clone(),
            after: Some(vec![model_in_database("order_lines", "archive")]),
            expected_decision: (
                false,
                true,
                "moves from database warehouse to archive; migrations cannot cross databases",
            ),
        },
        MigrationDecisionTestCase {
            description: "an emptied schema is blocked",
            before: before.clone(),
            after: Some(vec![model("order_lines", Some("table"), "marts")]),
            expected_decision: (
                false,
                true,
                "no model is left in schema analytics, so migrate_from orders cannot find the old relation; add a schema-qualified migrate_from for each target",
            ),
        },
    ];
    for test_case in test_cases {
        let decision = decide_model_migration(
            &test_case.before,
            test_case.after.as_deref(),
            ("orders", "order_lines"),
        );
        assert_eq!(
            (decision.needed, decision.blocked, decision.reason.as_str()),
            test_case.expected_decision,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_failing_commit_when_committing_then_project_files_are_unchanged()
-> Result<(), RefactorError> {
    let test_cases = [
        CommitTestCase {
            description: "a write failing after an earlier write restores every file",
            on_disk: &[
                ("models/orders.sql", "SELECT 1"),
                ("models/customers.sql", "SELECT 2"),
            ],
            originals: &[
                ("models/orders.sql", "SELECT 1"),
                ("models/customers.sql", "SELECT 2"),
            ],
            changes: vec![
                change(
                    "models/orders.sql",
                    "models/orders.sql",
                    vec![replace_all("SELECT 1", "SELECT 10")],
                ),
                change(
                    "models/orders.sql/customers.sql",
                    "models/customers.sql",
                    Vec::new(),
                ),
            ],
            expected_error: (RefactorErrorKind::Io, "", ""),
            expected_files: &[
                ("models/orders.sql", "SELECT 1"),
                ("models/customers.sql", "SELECT 2"),
            ],
        },
        CommitTestCase {
            description: "a file edited since planning writes nothing",
            on_disk: &[("models/orders.sql", "SELECT 3")],
            originals: &[("models/orders.sql", "SELECT 1")],
            changes: vec![change(
                "models/orders.sql",
                "models/orders.sql",
                vec![replace_all("SELECT 1", "SELECT 10")],
            )],
            expected_error: (
                RefactorErrorKind::Write,
                "C958",
                "files changed while the refactoring ran: models/orders.sql",
            ),
            expected_files: &[("models/orders.sql", "SELECT 3")],
        },
    ];
    for test_case in test_cases {
        let project =
            tempfile::tempdir().map_err(|error| RefactorError::value(error.to_string()))?;
        write_files(project.path(), test_case.on_disk)?;
        let failure = commit_failure(
            project.path(),
            test_case.originals,
            &test_case.changes,
            test_case.expected_error.2,
        );
        assert_eq!(
            failure,
            Some((
                test_case.expected_error.0,
                test_case.expected_error.1.to_owned(),
                true
            )),
            "{}",
            test_case.description
        );
        assert_eq!(
            files_on_disk(project.path(), test_case.on_disk),
            owned_pairs(test_case.expected_files),
            "{}",
            test_case.description
        );
    }
    Ok(())
}
