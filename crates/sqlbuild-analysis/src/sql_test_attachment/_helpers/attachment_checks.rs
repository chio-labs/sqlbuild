//! `helper_ctes`: the helper CTEs a model test reads and the references it cannot resolve.

use std::collections::{HashMap, HashSet, VecDeque};

use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::python_casefold::python_casefold;
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::{ReferenceExtraction, SqlReference};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::assembly::analysis_session::main::sql_test_helper_reads::sql_test_helper_reads;
use crate::compiler::models::SqlTestCteText;
use crate::sql_test_attachment::constants::{
    DBT_REF_KIND, MOCK_PREFIXES, REF_KIND, REF_PREFIX, SEED_KIND, SOURCE_KIND, TABLE_FUNCTION_KIND,
};
use crate::sql_test_attachment::models::{
    ModelTestCtes, SqlTestCheckFailure, SqlTestHelperProblem, SqlTestReadFacts,
};
use crate::sql_test_attachment::types::SqlTestTextMatcher;

type Checked<T, E> = Result<T, SqlTestCheckFailure<E>>;
/// The parsed reads, `None` where the body does not parse, and the reads used.
type CteReads = (Option<Vec<String>>, Vec<String>);

/// `SqlTestCteGraph`: the authored CTEs by casefolded name and what each one reads.
struct CteGraph<'a> {
    ctes: HashMap<String, &'a SqlTestCteText>,
    reads: HashMap<String, Vec<String>>,
    parsed_reads: HashMap<String, Vec<String>>,
    reader_reads: Vec<String>,
}

impl CteGraph<'_> {
    fn name(&self, key: &str) -> &str {
        self.ctes.get(key).map_or("", |cte| cte.0.as_str())
    }

    fn sql(&self, key: &str) -> &str {
        self.ctes.get(key).map_or("", |cte| cte.1.as_str())
    }

    /// `reachable_cte_keys`: the roots then what they read, breadth first, in visit order.
    fn reachable(&self, roots: &[String]) -> Vec<String> {
        let mut pending: VecDeque<String> = roots
            .iter()
            .filter(|root| self.ctes.contains_key(*root))
            .cloned()
            .collect();
        let mut visited: Vec<String> = Vec::new();
        for root in &pending {
            if !visited.contains(root) {
                visited.push(root.clone());
            }
        }
        while let Some(key) = pending.pop_front() {
            for dependency in self.reads.get(&key).into_iter().flatten() {
                if !visited.contains(dependency) {
                    visited.push(dependency.clone());
                    pending.push_back(dependency.clone());
                }
            }
        }
        visited
    }

    /// `_read_helper_keys`: reachable authored CTEs that are not mocks.
    fn read_helpers(&self) -> Vec<String> {
        self.reachable(&self.reader_reads)
            .into_iter()
            .filter(|key| !is_mock(self.name(key)))
            .collect()
    }
}

fn is_mock(name: &str) -> bool {
    MOCK_PREFIXES.iter().any(|prefix| name.starts_with(prefix))
}

fn casefold(text: &str) -> String {
    python_casefold(active_python_text(), text)
}

fn unique(items: impl IntoIterator<Item = String>) -> Vec<String> {
    let mut seen: HashSet<String> = HashSet::new();
    items
        .into_iter()
        .filter(|item| seen.insert(item.clone()))
        .collect()
}

/// `_parsed_reads` then `_token_reads` when the body does not parse.
fn cte_reads<M: SqlTestTextMatcher>(
    sql: &str,
    keys: &[String],
    matcher: &M,
) -> Checked<CteReads, M::Error> {
    let mut sorted: Vec<String> = keys.to_vec();
    sorted.sort();
    if let Some(parsed) =
        sql_test_helper_reads(sql, &sorted).map_err(SqlTestCheckFailure::Internal)?
    {
        return Ok((Some(parsed.clone()), parsed));
    }
    let tokens: Vec<String> = matcher
        .identifier_tokens(sql)
        .map_err(SqlTestCheckFailure::Matcher)?;
    Ok((
        None,
        tokens
            .into_iter()
            .filter(|token| keys.contains(token))
            .collect(),
    ))
}

/// `sql_test_cte_graph` over the test's authored CTEs and its expected and assertion readers.
fn cte_graph<'a, M: SqlTestTextMatcher>(
    payload: &ModelTestCtes<'a>,
    matcher: &M,
) -> Checked<CteGraph<'a>, M::Error> {
    let mut keys: Vec<String> = Vec::new();
    let mut ctes: HashMap<String, &'a SqlTestCteText> = HashMap::new();
    for cte in payload.authored {
        let key: String = casefold(&cte.0);
        if ctes.insert(key.clone(), cte).is_none() {
            keys.push(key);
        }
    }
    let mut reads: HashMap<String, Vec<String>> = HashMap::new();
    let mut parsed_reads: HashMap<String, Vec<String>> = HashMap::new();
    for key in &keys {
        let others: Vec<String> = keys.iter().filter(|other| *other != key).cloned().collect();
        let (parsed, read) = cte_reads(&ctes[key].1, &others, matcher)?;
        parsed_reads.insert(key.clone(), parsed.unwrap_or_default());
        reads.insert(key.clone(), read);
    }
    let mut reader_reads: Vec<String> = Vec::new();
    for reader in payload.readers() {
        reader_reads.extend(cte_reads(&reader.1, &keys, matcher)?.1);
    }
    let _ = keys;
    Ok(CteGraph {
        ctes,
        reads,
        parsed_reads,
        reader_reads: unique(reader_reads),
    })
}

/// `scan_sql_reference_calls(...).references`, raising the scan's unlocated error.
fn references<E>(sql: &str, syntax: &LexicalSyntax) -> Checked<Vec<SqlReference>, E> {
    match extract_sql_references(sql, syntax) {
        ReferenceExtraction::Extracted(scan) => Ok(scan.references),
        ReferenceExtraction::Failed(failure) => Err(SqlTestCheckFailure::Scan(failure.message)),
    }
}

/// `SqlReferenceKind.example_call(*args, quote='"')`.
fn example_call(kind: &str, arguments: &[&str]) -> String {
    let quoted: Vec<String> = arguments
        .iter()
        .map(|argument| format!("\"{}\"", argument.replace('"', "\"\"")))
        .collect();
    format!("__{kind}({})", quoted.join(", "))
}

/// `_reference_call`: a dbt reference names its package first.
fn reference_call(reference: &SqlReference) -> String {
    match (&reference.package, reference.kind) {
        (Some(package), DBT_REF_KIND) => example_call(DBT_REF_KIND, &[package, &reference.name]),
        _ => example_call(reference.kind, &[&reference.name]),
    }
}

/// `sql_test_reads`: the helpers a test reads and the unmocked models they and expected rows read.
pub(crate) fn sql_test_reads<M: SqlTestTextMatcher>(
    payload: &ModelTestCtes<'_>,
    syntax: &LexicalSyntax,
    matcher: &M,
) -> Checked<SqlTestReadFacts, M::Error> {
    let graph: CteGraph<'_> = cte_graph(payload, matcher)?;
    let read_helpers: Vec<String> = graph.read_helpers();
    let sqls = payload
        .expected
        .iter()
        .map(|cte| cte.1.as_str())
        .chain(read_helpers.iter().map(|key| graph.sql(key)));
    let mut targets: Vec<String> = Vec::new();
    for sql in sqls {
        for reference in references(sql, syntax)? {
            if reference.kind == REF_KIND && !payload.mock_models.contains(&reference.name) {
                targets.push(reference.name);
            }
        }
    }
    Ok(SqlTestReadFacts {
        read_helper_names: read_helpers
            .iter()
            .map(|key| graph.name(key).to_owned())
            .collect(),
        reference_target_model_names: unique(targets),
    })
}

/// `report_unresolvable_test_references`: each unresolvable reference, then any read cycle.
pub(crate) fn unresolvable_test_references<M: SqlTestTextMatcher>(
    payload: &ModelTestCtes<'_>,
    known_models: &HashSet<String>,
    syntax: &LexicalSyntax,
    matcher: &M,
) -> Checked<Vec<SqlTestHelperProblem>, M::Error> {
    let graph: CteGraph<'_> = cte_graph(payload, matcher)?;
    let read_helpers: Vec<String> = graph.read_helpers();
    let readers = read_helpers
        .iter()
        .map(|key| ("helper CTE", graph.name(key), graph.sql(key)))
        .chain(
            payload
                .expected
                .iter()
                .map(|cte| ("expected CTE", cte.0.as_str(), cte.1.as_str())),
        )
        .chain(
            payload
                .assertions
                .iter()
                .map(|cte| ("assertion CTE", cte.0.as_str(), cte.1.as_str())),
        );
    let mut problems: Vec<SqlTestHelperProblem> = Vec::new();
    for (label, name, sql) in readers {
        for reference in references(sql, syntax)? {
            let Some(mocked) = payload.mocked(reference.kind) else {
                continue;
            };
            let mock_name: String = match &reference.package {
                Some(package) => format!("{package}__{}", reference.name),
                None => reference.name.clone(),
            };
            if mocked.contains(&mock_name) {
                continue;
            }
            if reference.kind == REF_KIND {
                if known_models.contains(&reference.name) {
                    continue;
                }
                problems.push(SqlTestHelperProblem {
                    cte_name: name.to_owned(),
                    call: Some(example_call(REF_KIND, &[&reference.name])),
                    message: format!(
                        "SQL test {label} '{name}' references unknown model '{}'",
                        reference.name
                    ),
                    help: format!(
                        "Read a model defined in the project, for example __ref(\"<model>\"), or \
                         remove the reference from {label} '{name}'."
                    ),
                });
                continue;
            }
            let call: String = reference_call(&reference);
            problems.push(SqlTestHelperProblem {
                cte_name: name.to_owned(),
                call: Some(call.clone()),
                message: format!(
                    "SQL test {label} '{name}' calls {call}, which the test does not mock, so \
                     the test query cannot resolve it"
                ),
                help: format!(
                    "Mock it in the test, for example __{}__{mock_name} AS (SELECT ...), or \
                     remove the call from {label} '{name}'.",
                    reference.kind
                ),
            });
        }
    }
    let cycle: Option<Vec<String>> = if read_helpers.is_empty() {
        None
    } else {
        first_cycle(&graph, &graph.reachable(&graph.reader_reads))
    };
    if let Some(cycle) = cycle {
        let names: Vec<&str> = cycle.iter().map(|key| graph.name(key)).collect();
        let path: String = names
            .iter()
            .map(|name| format!("'{name}'"))
            .collect::<Vec<_>>()
            .join(" -> ");
        problems.push(SqlTestHelperProblem {
            cte_name: names[0].to_owned(),
            call: None,
            message: format!(
                "SQL test CTE '{}' reads itself through {path}, so the test query cannot define \
                 its CTEs in dependency order",
                names[0]
            ),
            help: "Break the cycle by moving the shared rows into a helper CTE that reads \
                   neither, for example shared_rows AS (SELECT ...), and read shared_rows from \
                   both CTEs."
                .to_owned(),
        });
    }
    Ok(problems)
}

/// `_first_cycle`: the first parsed read cycle among `keys`, closed on its first CTE.
fn first_cycle(graph: &CteGraph<'_>, keys: &[String]) -> Option<Vec<String>> {
    let allowed: HashSet<&String> = keys.iter().collect();
    for origin in keys {
        let mut pending: VecDeque<Vec<String>> = VecDeque::from([vec![origin.clone()]]);
        let mut visited: HashSet<String> = HashSet::new();
        while let Some(path) = pending.pop_front() {
            let last: &String = path.last()?;
            for dependency in graph.parsed_reads.get(last).into_iter().flatten() {
                if dependency == origin {
                    let mut closed: Vec<String> = path.clone();
                    closed.push(origin.clone());
                    return Some(closed);
                }
                if allowed.contains(dependency) && visited.insert(dependency.clone()) {
                    let mut next: Vec<String> = path.clone();
                    next.push(dependency.clone());
                    pending.push_back(next);
                }
            }
        }
    }
    None
}

/// `report_test_without_target_model`: the problem of a model test whose checks read only mocks.
pub(crate) fn test_without_target_model<M: SqlTestTextMatcher>(
    payload: &ModelTestCtes<'_>,
    test_name: &str,
    syntax: &LexicalSyntax,
    matcher: &M,
) -> Checked<SqlTestHelperProblem, M::Error> {
    let graph: CteGraph<'_> = cte_graph(payload, matcher)?;
    let mut read_mocks: Vec<String> = graph
        .reachable(&graph.reader_reads)
        .iter()
        .map(|key| graph.name(key).to_owned())
        .filter(|name| is_mock(name))
        .collect();
    let mut first_calls: Vec<(&'static str, (String, String))> = Vec::new();
    let mut called_models: HashSet<String> = HashSet::new();
    for reader in payload.readers() {
        for reference in references(&reader.1, syntax)? {
            let mocked: bool = payload
                .mocked(reference.kind)
                .or_else(|| {
                    (reference.kind == TABLE_FUNCTION_KIND).then_some(payload.mock_table_functions)
                })
                .is_some_and(|names| names.contains(&reference.name));
            if !mocked {
                continue;
            }
            read_mocks.push(format!("__{}__{}", reference.kind, reference.name));
            if reference.kind == REF_KIND {
                called_models.insert(reference.name.clone());
            }
            if reference.kind != TABLE_FUNCTION_KIND
                && !first_calls.iter().any(|(kind, _)| *kind == reference.kind)
            {
                first_calls.push((
                    reference.kind,
                    (reader.0.clone(), reference_call(&reference)),
                ));
            }
        }
    }
    let mocks: Vec<String> = unique(read_mocks);
    let mocked_models: Vec<&str> = mocks
        .iter()
        .filter_map(|mock| mock.strip_prefix(REF_PREFIX))
        .collect();
    let located: Option<(String, String)> =
        match first_calls.iter().find(|(kind, _)| *kind == REF_KIND) {
            Some((_, call)) => Some(call.clone()),
            None => match mock_name_read(payload, &mocks, matcher)? {
                Some(read) => Some(read),
                None => first_calls.first().map(|(_, call)| call.clone()),
            },
        };
    let (message, help) = if mocked_models.is_empty() {
        let reads: String = if mocks.is_empty() {
            "reads no model".to_owned()
        } else {
            format!("reads only mocks ({})", mocks.join(", "))
        };
        (
            format!("SQL test '{test_name}' {reads}, so the test has no model to run against"),
            "Call __ref(\"<model under test>\") in an __assert__ or __expected__ CTE so the test \
             runs that model with its mocks, or remove the test."
                .to_owned(),
        )
    } else {
        let plural: &str = if mocked_models.len() > 1 { "s" } else { "" };
        let owner: &str = if plural.is_empty() {
            "model's"
        } else {
            "models'"
        };
        let verb: &str = if mocked_models
            .iter()
            .all(|name| called_models.contains(*name))
        {
            "keep"
        } else {
            "call"
        };
        let mocked_ctes: String = mocked_models
            .iter()
            .map(|name| format!("{REF_PREFIX}{name}"))
            .collect::<Vec<_>>()
            .join(", ");
        let calls: String = mocked_models
            .iter()
            .map(|name| example_call(REF_KIND, &[name]))
            .collect::<Vec<_>>()
            .join(" and ");
        (
            format!(
                "SQL test '{test_name}' mocks the model{plural} it tests ({mocked_ctes}), so the \
                 test has no model to run against"
            ),
            format!(
                "Mock the {owner} inputs instead (for example __source__<source> or \
                 __ref__<upstream model>) and {verb} {calls} in the __assert__ or __expected__ \
                 CTE, or remove the test."
            ),
        )
    };
    let (cte_name, call) = match located {
        Some((cte, call)) => (cte, Some(call)),
        None => (
            payload
                .readers()
                .next()
                .map_or_else(|| test_name.to_owned(), |reader| reader.0.clone()),
            None,
        ),
    };
    Ok(SqlTestHelperProblem {
        cte_name,
        call,
        message,
        help,
    })
}

/// `_mock_name_read`: the first check reading a mocked model by its CTE name.
fn mock_name_read<M: SqlTestTextMatcher>(
    payload: &ModelTestCtes<'_>,
    mocks: &[String],
    matcher: &M,
) -> Checked<Option<(String, String)>, M::Error> {
    for mock in mocks.iter().filter(|mock| mock.starts_with(REF_PREFIX)) {
        for reader in payload.readers() {
            if matcher
                .reads_word(&reader.1, mock)
                .map_err(SqlTestCheckFailure::Matcher)?
            {
                return Ok(Some((reader.0.clone(), mock.clone())));
            }
        }
    }
    Ok(None)
}

impl<'a> ModelTestCtes<'a> {
    /// `_reader_ctes`: the expected, then assertion, CTEs.
    pub(crate) fn readers(&self) -> impl Iterator<Item = &'a SqlTestCteText> {
        self.expected.iter().chain(self.assertions.iter())
    }

    /// The mocked names of a `ref`, `source`, `seed` or `dbt_ref` reference kind.
    fn mocked(&self, kind: &str) -> Option<&'a [String]> {
        match kind {
            REF_KIND => Some(self.mock_models),
            SOURCE_KIND => Some(self.mock_sources),
            SEED_KIND => Some(self.mock_seeds),
            DBT_REF_KIND => Some(self.mock_dbt_refs),
            _ => None,
        }
    }
}
