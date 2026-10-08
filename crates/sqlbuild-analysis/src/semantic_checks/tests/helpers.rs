use std::collections::BTreeSet;

use polyglot_sql::{DialectType, SchemaValidationOptions};

use crate::semantic_checks::_helpers::messages::{missing_column, sentence_message};
use crate::semantic_checks::_helpers::parsed_sql::parsed_model_facts;
use crate::semantic_checks::main::complete_semantic_diagnostics::complete_semantic_diagnostics;
use crate::semantic_checks::main::finish_type_recovery::finish_type_recovery;
use crate::semantic_checks::main::plan_type_recovery::plan_type_recovery;
use crate::semantic_checks::models::{
    CompletedDiagnostic, CompletionModel, CompletionRequest, DiagnosticOwner, FinalDiagnostic,
    LineageOutput, ModelBinding, RawBinding, RecoveryModel, SemanticDeferral, SemanticDiagnostic,
    SemanticLocation, TypeRecoveryPlan, TypeRecoveryRequest,
};
use crate::semantic_checks::tests::test_types::{
    CompletionTestCase, DescribedDiagnostic, TypeRecoveryTestCase,
};
use crate::semantic_validation::models::ProjectCatalog;

/// What type recovery decided: status, poisoned outputs, revalidated models, kept and bindings.
pub(crate) type RecoverySummary = (
    &'static str,
    Vec<(String, String)>,
    Vec<usize>,
    Vec<(usize, Option<String>)>,
    Vec<Vec<usize>>,
);

/// What completion decided: deferral, final diagnostics and model binding positions.
pub(crate) type CompletionSummary = (
    Option<&'static str>,
    Vec<DescribedDiagnostic>,
    Option<Vec<Vec<usize>>>,
);

pub(crate) fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

pub(crate) fn shape(columns: &[(&str, &str)]) -> Vec<(String, String)> {
    columns
        .iter()
        .map(|(name, kind)| ((*name).to_owned(), (*kind).to_owned()))
        .collect()
}

pub(crate) fn pairs(values: &[(&str, &str)]) -> BTreeSet<(String, String)> {
    shape(values).into_iter().collect()
}

pub(crate) fn names(values: &[&str]) -> BTreeSet<String> {
    strings(values).into_iter().collect()
}

pub(crate) fn sentence(message: &str) -> Result<String, SemanticDeferral> {
    sentence_message(message)
}

/// The missing column and table Python reads from a message.
pub(crate) fn missing_parts(
    message: &str,
) -> Result<Option<(String, Option<String>)>, SemanticDeferral> {
    missing_column(message)
}

/// An expected missing column and table as owned strings.
pub(crate) fn owned_missing(
    expected: Result<Option<(&str, Option<&str>)>, SemanticDeferral>,
) -> Result<Option<(String, Option<String>)>, SemanticDeferral> {
    expected.map(|missing| missing.map(owned_parts))
}

fn owned_parts((column, table): (&str, Option<&str>)) -> (String, Option<String>) {
    (column.to_owned(), table.map(str::to_owned))
}

/// Aliases and unaliased outputs of one DuckDB model.
pub(crate) fn parsed_facts(sql: &str) -> (BTreeSet<(String, String)>, BTreeSet<String>) {
    let facts = parsed_model_facts(sql, Some("duckdb")).expect("duckdb parses");
    (
        facts.aliases.into_iter().collect(),
        facts.unaliased_outputs.into_iter().collect(),
    )
}

pub(crate) fn catalog() -> ProjectCatalog {
    ProjectCatalog::with_options(
        DialectType::DuckDB,
        SchemaValidationOptions::default(),
        false,
    )
}

pub(crate) fn lineage(output: &str, upstream: &[(&str, &str)]) -> LineageOutput {
    LineageOutput {
        output_column: output.to_owned(),
        upstream: shape(upstream),
    }
}

fn recovery_model(
    name: &str,
    query_sql: &str,
    references: &[&str],
    lineage: Vec<LineageOutput>,
    binding: Option<(usize, &str, i64, i64)>,
    is_error: bool,
) -> RecoveryModel {
    let message = |code: &str| format!("{code} failed");
    RecoveryModel {
        name: name.to_owned(),
        query_sql: query_sql.to_owned(),
        inferred_columns: Some(
            lineage
                .iter()
                .map(|output| output.output_column.clone())
                .collect(),
        ),
        references: strings(references),
        lineage,
        bindings: binding
            .iter()
            .map(|(id, code, _, _)| ModelBinding {
                id: *id,
                code: (*code).to_owned(),
                message: message(code),
                is_error,
            })
            .collect(),
        raw_bindings: binding
            .iter()
            .map(|(id, code, start, end)| RawBinding {
                id: *id,
                code: (*code).to_owned(),
                message: message(code),
                start: Some(*start),
                end: Some(*end),
            })
            .collect(),
    }
}

fn owner(id: usize, code: &str, model: &str) -> DiagnosticOwner {
    DiagnosticOwner {
        id,
        code: code.to_owned(),
        is_model: true,
        resource_name: Some(model.to_owned()),
    }
}

/// A staging projection type error poisoning a mart output and a report reading it.
fn poisoned_chain(dialect: Option<&str>, is_error: bool) -> TypeRecoveryRequest {
    TypeRecoveryRequest {
        dialect: dialect.map(str::to_owned),
        models: vec![
            recovery_model(
                "stg",
                "SELECT order_id, amount + 'x' AS amount FROM __source(\"raw_orders\")",
                &["raw_orders"],
                vec![
                    lineage("order_id", &[("raw_orders", "order_id")]),
                    lineage("amount", &[("raw_orders", "amount")]),
                ],
                Some((0, "B212", 17, 29)),
                is_error,
            ),
            recovery_model(
                "mart",
                "SELECT customer_id, SUM(amount) AS total FROM __ref(\"stg\") WHERE amount > 5 GROUP BY 1",
                &["stg"],
                vec![
                    lineage("customer_id", &[("stg", "customer_id")]),
                    lineage("total", &[("stg", "amount")]),
                ],
                Some((1, "B217", 56, 62)),
                is_error,
            ),
            recovery_model(
                "report",
                "SELECT total AS x FROM __ref(\"mart\")",
                &["mart"],
                vec![lineage("x", &[("mart", "total")])],
                None,
                is_error,
            ),
        ],
        diagnostics: vec![owner(0, "B212", "stg"), owner(1, "B217", "mart")],
    }
}

/// Plan and finish type recovery for one case of the poisoned chain.
pub(crate) fn recovery_summary(test_case: &TypeRecoveryTestCase) -> RecoverySummary {
    let request = poisoned_chain(test_case.dialect, test_case.errors);
    let step = plan_type_recovery(&request, &catalog()).expect("the analysis pool runs");
    let revised = vec![
        test_case
            .revised
            .iter()
            .map(|(code, start, end)| ((*code).to_owned(), *start, *end))
            .collect(),
    ];
    let outcome = step
        .plan()
        .map(|plan| finish_type_recovery(&request, plan, &revised).expect("finishes"))
        .unwrap_or_default();
    (
        step.deferral().unwrap_or(step.status()),
        step.plan()
            .map(TypeRecoveryPlan::poisoned_outputs)
            .unwrap_or_default(),
        step.plan()
            .map(TypeRecoveryPlan::revalidated_models)
            .unwrap_or_default(),
        outcome.kept,
        outcome.model_bindings,
    )
}

/// Expected poisoned outputs as owned pairs, in order.
pub(crate) fn expected_poisoned(values: &[(&str, &str)]) -> Vec<(String, String)> {
    shape(values)
}

/// Expected retained diagnostics with owned notes.
pub(crate) fn expected_kept(values: &[(usize, Option<&str>)]) -> Vec<(usize, Option<String>)> {
    values
        .iter()
        .map(|(index, note)| (*index, note.map(str::to_owned)))
        .collect()
}

/// Expected model binding positions as owned vectors.
pub(crate) fn expected_bindings(values: &[&[usize]]) -> Vec<Vec<usize>> {
    values.iter().map(|positions| positions.to_vec()).collect()
}

/// A model diagnostic located at `(line, column)`.
fn model_diagnostic(
    id: usize,
    code: &str,
    message: &str,
    model: &str,
    location: Option<(i64, i64)>,
) -> SemanticDiagnostic {
    SemanticDiagnostic {
        id,
        code: code.to_owned(),
        message: message.to_owned(),
        resource_type: Some("model".to_owned()),
        resource_name: Some(model.to_owned()),
        line: location.map(|(line, _)| line),
        column: location.map(|(_, column)| column),
        location: location.map(|(line, column)| SemanticLocation {
            line,
            column,
            end_line: None,
            end_column: None,
        }),
        help: None,
        notes: Vec::new(),
    }
}

/// A model with its authored SQL behind a MODEL header.
fn completion_model(
    name: &str,
    query_sql: &str,
    inferred: &[&str],
    lineage: Vec<LineageOutput>,
    binding_codes: &[&str],
) -> CompletionModel {
    CompletionModel {
        name: name.to_owned(),
        query_sql: query_sql.to_owned(),
        authored_sql: format!("MODEL (\n  description \"{name}\",\n);\n\n{query_sql}\n"),
        inferred_columns: strings(inferred),
        lineage,
        binding_codes: strings(binding_codes),
        rejected_opt_out_file: None,
    }
}

/// A staging typo poisoning a mart use, a temporal comparison, a rejected opt-out and a test error.
fn project_request() -> CompletionRequest {
    let mut legacy = completion_model(
        "legacy",
        "SELECT mystery(order_id) AS m FROM __ref(\"stg\")",
        &["m"],
        Vec::new(),
        &["B101"],
    );
    legacy.rejected_opt_out_file = Some("legacy.sql".to_owned());
    let mut sql_test = model_diagnostic(
        4,
        "B002",
        "Unknown column 'x' in table 'stg'",
        "report",
        None,
    );
    sql_test.resource_type = Some("sql_test".to_owned());
    CompletionRequest {
        dialect: Some("duckdb".to_owned()),
        diagnostics: vec![
            model_diagnostic(
                0,
                "B002",
                "Unknown column 'amonut' in table 'raw_orders'",
                "stg",
                Some((5, 18)),
            ),
            model_diagnostic(
                1,
                "B002",
                "Unknown column 'amount' in table 'stg'",
                "mart",
                Some((5, 24)),
            ),
            model_diagnostic(
                2,
                "B217",
                "Cannot compare timestamp and integer (context: o.ordered_at > 5)",
                "mart",
                Some((7, 7)),
            ),
            model_diagnostic(
                3,
                "B101",
                "Unknown function 'mystery'",
                "legacy",
                Some((5, 8)),
            ),
            sql_test,
        ],
        models: vec![
            completion_model(
                "stg",
                "SELECT order_id, amonut, ordered_at FROM __source(\"raw_orders\")",
                &["order_id", "amonut", "ordered_at"],
                vec![lineage("amonut", &[("raw_orders", "amonut")])],
                &["B002"],
            ),
            completion_model(
                "mart",
                "SELECT customer_id, SUM(amount) AS total\nFROM __ref(\"stg\") AS o\n\
                 WHERE o.ordered_at > 5\nGROUP BY 1",
                &["customer_id", "total"],
                vec![lineage("total", &[("stg", "amount")])],
                &["B002", "B217"],
            ),
            legacy,
        ],
        shapes: vec![
            (
                "raw_orders".to_owned(),
                shape(&[
                    ("order_id", "INTEGER"),
                    ("customer_id", "INTEGER"),
                    ("amount", "DOUBLE"),
                    ("status", "VARCHAR"),
                ]),
            ),
            (
                "stg".to_owned(),
                shape(&[
                    ("order_id", "INTEGER"),
                    ("amount", "UNKNOWN"),
                    ("ordered_at", "TIMESTAMP"),
                ]),
            ),
        ],
    }
}

/// One expected diagnostic of the completion project.
pub(crate) fn described(
    code: &str,
    message: &str,
    help: Option<&str>,
    notes: &[&str],
    location: Option<(i64, i64, Option<i64>, Option<i64>)>,
) -> DescribedDiagnostic {
    (
        code.to_owned(),
        message.to_owned(),
        help.map(str::to_owned),
        strings(notes),
        location,
    )
}

/// Complete one variant of the project request.
pub(crate) fn completion_summary(test_case: &CompletionTestCase) -> CompletionSummary {
    let mut request = project_request();
    request.models[1]
        .authored_sql
        .push_str(["", "-- caf\u{e9}\n"][usize::from(test_case.non_ascii_comment)]);
    let kept_diagnostics =
        [request.diagnostics.len(), 0][usize::from(test_case.without_diagnostics)];
    request.diagnostics.truncate(kept_diagnostics);
    request.models[2].rejected_opt_out_file =
        [Some("legacy.sql".to_owned()), None][usize::from(test_case.without_diagnostics)].clone();
    let outcome = complete_semantic_diagnostics(&request, &catalog()).expect("the pool runs");
    let (deferral, parts) = outcome.into_parts();
    let (diagnostics, model_bindings, order) = parts.unwrap_or_default();
    let described_order: Vec<DescribedDiagnostic> = order
        .into_iter()
        .map(|entry| described_entry(&request, &diagnostics, entry))
        .collect();
    (deferral, described_order, model_bindings)
}

fn described_entry(
    request: &CompletionRequest,
    diagnostics: &[CompletedDiagnostic],
    entry: FinalDiagnostic,
) -> DescribedDiagnostic {
    let (position, opt_out) = entry.into_parts();
    let completed = position.map(|position| described_completed(request, &diagnostics[position]));
    let rejected = opt_out.map(|opt_out| {
        (
            "P009".to_owned(),
            opt_out.message,
            Some(opt_out.help),
            vec![opt_out.note],
            None,
        )
    });
    completed
        .or(rejected)
        .expect("one side of an order entry is set")
}

fn described_completed(
    request: &CompletionRequest,
    diagnostic: &CompletedDiagnostic,
) -> DescribedDiagnostic {
    (
        request.diagnostics[diagnostic.source].code.clone(),
        diagnostic.message.clone(),
        diagnostic.help.clone(),
        diagnostic.notes.clone(),
        diagnostic.location.map(|location| {
            (
                location.line,
                location.column,
                location.end_line,
                location.end_column,
            )
        }),
    )
}
