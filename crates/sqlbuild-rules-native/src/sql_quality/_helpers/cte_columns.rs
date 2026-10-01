//! SQBRSQL042: output columns of non-final CTEs that no later step reads.

use std::borrow::Cow;
use std::collections::{HashMap, HashSet};

use polyglot_sql::expressions::{Cte, JoinKind, Select};
use polyglot_sql::scope::walk_in_scope;
use polyglot_sql::{Expression, ExpressionWalk};

use crate::sql_lint::models::{LintDiagnostic, LintEdit};
use crate::sql_quality::constants::{
    DISTINCT_UNUSED_REMEDIATION, GROUP_BY_ALL_UNUSED_REMEDIATION, GROUP_KEY_UNUSED_REMEDIATION,
    INTERPOLATION_SENTINEL_PREFIXES, UNUSED_CTE_OUTPUT,
};
use crate::sql_quality::models::QualityRequest;
use crate::sql_quality::removal_safety::{expression_refusal, reads_whole_rows, select_refusal};
use crate::sql_quality::syntax::{
    Projection, columns, cte_select_tokens, lower, projection_removal, projections, qualifier,
    sources,
};
use crate::sql_tokens::main::projection_spans::projection_spans;

const HARNESS_PREFIX: &str = "__";
const COLUMNS_FUNCTION: &str = "COLUMNS";
const LAYOUT_FIX_REFUSAL: &str = "The projection list could not be mapped to authored tokens";

/// What one later step reads from a CTE.
#[derive(Default)]
struct Usage {
    names: HashSet<String>,
    everything: bool,
    passes_to: Vec<String>,
    read: bool,
}

impl Usage {
    fn merged(mut self, other: Self) -> Self {
        self.names.extend(other.names);
        self.everything |= other.everything;
        self.passes_to.extend(other.passes_to);
        self.read |= other.read;
        self
    }
}

/// One CTE whose unused outputs are being reported.
struct CteOutputs<'a> {
    cte: &'a Cte,
    name: &'a str,
    usage: Option<&'a Usage>,
}

pub(crate) fn diagnostics(request: &QualityRequest<'_>) -> Vec<LintDiagnostic> {
    if request.fixture_body {
        return Vec::new();
    }
    let mut found: Vec<LintDiagnostic> = Vec::new();
    for statement in request.statements {
        let Expression::Select(root) = statement else {
            continue;
        };
        let Some(with) = root.with.as_ref().filter(|with| !with.recursive) else {
            continue;
        };
        let mut terminal: Select = root.as_ref().clone();
        terminal.with = None;
        let terminal: Expression = Expression::Select(Box::new(terminal));
        let names: Vec<String> = with.ctes.iter().map(|cte| lower(&cte.alias.name)).collect();
        let used: HashMap<String, Usage> = reads(&with.ctes, &names, &terminal);
        let select_tokens: HashMap<String, usize> = cte_select_tokens(request.tokens);
        for (index, cte) in with
            .ctes
            .iter()
            .enumerate()
            .take(with.ctes.len().saturating_sub(1))
        {
            let name: &str = &names[index];
            if name.starts_with(HARNESS_PREFIX) || request.externally_referenced_ctes.contains(name)
            {
                continue;
            }
            found.extend(unused_outputs(
                request,
                &select_tokens,
                CteOutputs {
                    cte,
                    name,
                    usage: used.get(name),
                },
            ));
        }
    }
    found
}

/// Names each CTE's later readers use, following `SELECT *` pass-through to the reader.
fn reads(ctes: &[Cte], names: &[String], terminal: &Expression) -> HashMap<String, Usage> {
    let bodies: Vec<(Option<String>, &Expression)> = ctes
        .iter()
        .map(|cte| (Some(lower(&cte.alias.name)), &cte.this))
        .chain(std::iter::once((None, terminal)))
        .collect();
    let known: HashSet<&str> = names.iter().map(String::as_str).collect();
    let outputs: Vec<Option<HashSet<String>>> = ctes.iter().map(output_names).collect();
    let mut readers: HashMap<String, Vec<usize>> = HashMap::new();
    for (index, (_, body)) in bodies.iter().enumerate() {
        for name in read_relations(body) {
            if known.contains(name.as_str()) {
                readers.entry(name).or_default().push(index);
            }
        }
    }
    let mut usage: HashMap<String, Usage> = HashMap::new();
    for (index, name) in names.iter().enumerate() {
        let mut current: Usage = Usage::default();
        if index + 1 == names.len() {
            current.everything = true;
        }
        for &reader in readers.get(name.as_str()).into_iter().flatten() {
            if reader > index {
                let (reader_name, body) = &bodies[reader];
                let target: Target<'_> = Target {
                    name,
                    outputs: outputs[index].as_ref(),
                };
                current = current.merged(reader_usage(&target, reader_name.clone(), body));
            }
        }
        current.names.extend(self_reads(&ctes[index].this));
        usage.insert(name.clone(), current);
    }
    for index in (0..names.len()).rev() {
        let passes: Vec<String> = usage[&names[index]].passes_to.clone();
        for reader in passes {
            let (everything, inherited): (bool, Vec<String>) =
                usage.get(&reader).map_or((true, Vec::new()), |next| {
                    (next.everything, next.names.iter().cloned().collect())
                });
            if let Some(current) = usage.get_mut(&names[index]) {
                current.everything |= everything;
                current.names.extend(inherited);
            }
        }
    }
    usage
}

/// The output names of a CTE, or None when a star or unnamed projection hides them.
fn output_names(cte: &Cte) -> Option<HashSet<String>> {
    let Expression::Select(select) = &cte.this else {
        return None;
    };
    projections(select)
        .into_iter()
        .map(|item| match item {
            Projection::Named { name, .. } => Some(name),
            _ => None,
        })
        .collect()
}

fn read_relations(body: &Expression) -> HashSet<String> {
    body.dfs()
        .filter_map(|node| match node {
            Expression::Table(table) => Some(lower(&table.name.name)),
            _ => None,
        })
        .collect()
}

/// The CTE whose readers are being inspected.
struct Target<'a> {
    name: &'a str,
    outputs: Option<&'a HashSet<String>>,
}

fn reader_usage(target: &Target<'_>, reader: Option<String>, body: &Expression) -> Usage {
    let name: &str = target.name;
    let mut usage: Usage = Usage::default();
    let mut aliases: HashSet<String> = HashSet::new();
    let mut top_level_star: bool = false;
    for node in body.dfs() {
        let Expression::Select(select) = node else {
            continue;
        };
        let local: Vec<String> = sources(select)
            .into_iter()
            .filter(|(_, relation, _)| relation.as_deref() == Some(name))
            .map(|(alias, _, _)| alias)
            .collect();
        if local.is_empty() {
            continue;
        }
        if select.joins.iter().any(|join| {
            matches!(
                join.kind,
                JoinKind::Natural
                    | JoinKind::NaturalLeft
                    | JoinKind::NaturalRight
                    | JoinKind::NaturalFull
            )
        }) {
            usage.everything = true;
        }
        for join in &select.joins {
            usage
                .names
                .extend(join.using.iter().map(|identifier| lower(&identifier.name)));
        }
        let top: bool = std::ptr::eq(node, body);
        if reads_as_row(select, &local, target.outputs) {
            usage.everything = true;
        }
        for projection in projections(select) {
            if let Projection::Star(star) = projection
                && star
                    .table
                    .as_ref()
                    .is_none_or(|table| local.contains(&lower(&table.name)))
            {
                if top
                    && reader.is_some()
                    && star.except.is_none()
                    && star.replace.is_none()
                    && !reads_whole_rows(select)
                {
                    top_level_star = true;
                } else {
                    usage.everything = true;
                }
            }
        }
        aliases.extend(local);
    }
    if aliases.is_empty() {
        return usage;
    }
    usage.read = true;
    usage.everything |= columns(body)
        .into_iter()
        .any(|column| is_interpolation(&column.name.name));
    if top_level_star && let Some(reader) = reader {
        usage.passes_to.push(reader);
    }
    for column in body.dfs().filter_map(|node| match node {
        Expression::Column(column) => Some(column),
        _ => None,
    }) {
        if qualifier(column).is_none_or(|table| aliases.contains(&table)) {
            usage.names.insert(lower(&column.name.name));
        }
    }
    usage
}

/// Whether a reader consumes whole rows: a nested star, `COLUMNS(...)`, or the alias itself.
fn reads_as_row(select: &Select, local: &[String], outputs: Option<&HashSet<String>>) -> bool {
    for clause in clause_roots(select) {
        for node in walk_in_scope(clause, false) {
            if reads_row_at(select, node, local, outputs) {
                return true;
            }
        }
    }
    false
}

fn reads_row_at(
    select: &Select,
    node: &Expression,
    local: &[String],
    outputs: Option<&HashSet<String>>,
) -> bool {
    match node {
        Expression::Star(star) => {
            let projected: bool = select
                .expressions
                .iter()
                .any(|item| std::ptr::eq(item, node));
            let table: Option<String> = star.table.as_ref().map(|table| lower(&table.name));
            !projected && table.is_none_or(|table| local.contains(&table))
        }
        Expression::BracedWildcard(_) => true,
        Expression::Function(function) => function.name.eq_ignore_ascii_case(COLUMNS_FUNCTION),
        Expression::Column(column) => {
            let read: String = lower(&column.name.name);
            let named_output: bool = outputs.is_some_and(|names| names.contains(&read));
            column.table.is_none() && local.contains(&read) && !named_output
        }
        _ => false,
    }
}

/// Root expressions of every clause of one select, without its FROM relations.
fn clause_roots(select: &Select) -> Vec<&Expression> {
    let mut roots: Vec<&Expression> = select.expressions.iter().collect();
    roots.extend(select.where_clause.iter().map(|clause| &clause.this));
    roots.extend(select.having.iter().map(|clause| &clause.this));
    roots.extend(select.qualify.iter().map(|clause| &clause.this));
    if let Some(group) = &select.group_by {
        roots.extend(group.expressions.iter());
    }
    if let Some(order) = &select.order_by {
        roots.extend(order.expressions.iter().map(|ordered| &ordered.this));
    }
    roots.extend(select.joins.iter().filter_map(|join| join.on.as_ref()));
    roots
}

/// Lateral alias reuse: a later projection or a clause of the CTE reading an earlier output.
fn self_reads(body: &Expression) -> HashSet<String> {
    let mut reads: HashSet<String> = HashSet::new();
    let Expression::Select(select) = body else {
        return reads;
    };
    let mut earlier: HashSet<String> = HashSet::new();
    for item in projections(select) {
        if let Projection::Named { name, expression } = item {
            for read in unqualified_reads(expression) {
                if earlier.contains(&read) && read != name {
                    reads.insert(read);
                }
            }
            earlier.insert(name);
        }
    }
    let mut clauses: Vec<&Expression> = Vec::new();
    clauses.extend(select.where_clause.iter().map(|clause| &clause.this));
    clauses.extend(
        select
            .group_by
            .iter()
            .flat_map(|group| group.expressions.iter()),
    );
    clauses.extend(select.having.iter().map(|clause| &clause.this));
    clauses.extend(select.qualify.iter().map(|clause| &clause.this));
    if let Some(order) = &select.order_by {
        clauses.extend(order.expressions.iter().map(|ordered| &ordered.this));
    }
    for clause in clauses {
        reads.extend(
            unqualified_reads(clause)
                .into_iter()
                .filter(|read| earlier.contains(read)),
        );
    }
    reads
}

fn unqualified_reads(expression: &Expression) -> Vec<String> {
    columns(expression)
        .into_iter()
        .filter(|column| qualifier(column).is_none())
        .map(|column| lower(&column.name.name))
        .collect()
}

fn unused_outputs(
    request: &QualityRequest<'_>,
    select_tokens: &HashMap<String, usize>,
    outputs: CteOutputs<'_>,
) -> Vec<LintDiagnostic> {
    let CteOutputs { cte, name, usage } = outputs;
    let Expression::Select(select) = &cte.this else {
        return Vec::new();
    };
    let Some(usage) = usage.filter(|usage| !usage.everything && usage.read) else {
        return Vec::new();
    };
    if !cte.columns.is_empty() {
        return Vec::new();
    }
    let output: Vec<Projection<'_>> = projections(select);
    if !output
        .iter()
        .all(|item| matches!(item, Projection::Named { .. }))
    {
        return Vec::new();
    }
    let spans: Vec<(usize, usize)> = select_tokens
        .get(name)
        .map(|&select_token| projection_spans(request.tokens, select_token))
        .unwrap_or_default();
    let grouped: HashSet<String> = select
        .group_by
        .iter()
        .flat_map(|group| group.expressions.iter())
        .flat_map(columns)
        .map(|column| lower(&column.name.name))
        .collect();
    let select_refused: Option<&'static str> = select_refusal(select, output.len());
    let mut found: Vec<LintDiagnostic> = Vec::new();
    for (index, item) in output.iter().enumerate() {
        let Projection::Named {
            name: column,
            expression,
        } = item
        else {
            continue;
        };
        if usage.names.contains(column) || is_interpolation(column) {
            continue;
        }
        let grouping_key: bool = matches!(expression, Expression::Column(source) if grouped.contains(&lower(&source.name.name)));
        let (start, end) = spans
            .get(index)
            .copied()
            .filter(|_| spans.len() == output.len())
            .unwrap_or((0, 0));
        let refusal: Option<&'static str> = select_refused
            .or_else(|| expression_refusal(expression))
            .or_else(|| (spans.len() != output.len()).then_some(LAYOUT_FIX_REFUSAL));
        let fix: Option<LintEdit> = refusal
            .is_none()
            .then(|| projection_removal(&spans, index))
            .flatten()
            .map(|(start, end)| LintEdit {
                start,
                end,
                replacement: String::new(),
            });
        found.push(LintDiagnostic {
            code: UNUSED_CTE_OUTPUT.code,
            message: UNUSED_CTE_OUTPUT.message,
            remediation: Cow::Borrowed(if select.distinct {
                DISTINCT_UNUSED_REMEDIATION
            } else if select
                .group_by
                .as_ref()
                .is_some_and(|group| group.all == Some(true))
            {
                GROUP_BY_ALL_UNUSED_REMEDIATION
            } else if grouping_key {
                GROUP_KEY_UNUSED_REMEDIATION
            } else {
                UNUSED_CTE_OUTPUT.remediation
            }),
            start,
            end,
            fix_unavailable_reason: if fix.is_none() {
                Some(refusal.unwrap_or(LAYOUT_FIX_REFUSAL))
            } else {
                None
            },
            fix,
        });
    }
    found
}

/// Neutralized `@macro` / `@variable` interpolations can stand for any columns.
fn is_interpolation(name: &str) -> bool {
    let name: String = lower(name);
    INTERPOLATION_SENTINEL_PREFIXES
        .iter()
        .any(|prefix| name.starts_with(prefix))
}
