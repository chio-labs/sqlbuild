//! Helper and mock CTEs placed in scope for SQL-test queries, in dependency order.

use std::collections::{BTreeMap, HashMap, HashSet};

use crate::compiler::_helpers::sql_tests::cte_sql::{parenthesized_sql, with_leading_ctes};
use crate::compiler::_helpers::sql_tests::markers::{in_protected_range, protected_ranges};
use crate::compiler::_helpers::sql_tests::planning::{
    DBT_REF_PREFIX, REF_PREFIX, SEED_PREFIX, SOURCE_PREFIX, SqlTestPatterns, TestFixtures,
    compile_error,
};
use crate::constants::{
    QUOTED_IDENTIFIER_DELIMITER_BYTES, SQL_TEST_ACTUAL_CTE, SQL_TEST_ACTUAL_CTE_PREFIX,
    SQL_TEST_EXPECTED_CTE,
};

/// Helper CTEs, and the mocks they read by CTE name, that one test query needs in scope.
pub(crate) struct HelperScope {
    pub(crate) ctes: Vec<(String, String)>,
    pub(crate) reached_mocks: HashSet<String>,
}

/// One mock CTE other test CTEs can read by its generated name.
pub(crate) struct ScopeMock {
    pub(crate) generated_name: String,
    pub(crate) mock_name: String,
    pub(crate) sql: String,
    tokens: Vec<String>,
}

/// One test CTE another test CTE reads: a mock, or a helper when `mock_name` is `None`.
pub(crate) struct ScopeDependency<'a> {
    pub(crate) generated_name: &'a str,
    pub(crate) mock_name: Option<&'a str>,
    pub(crate) sql: &'a str,
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
enum ScopeNode {
    Helper(usize),
    Mock(usize),
}

/// Name references between one test's helper and mock CTEs, tokenized once per test.
#[derive(Default)]
pub(crate) struct ScopeGraph {
    helpers: Vec<(String, String)>,
    helper_tokens: Vec<Vec<String>>,
    helper_indexes: HashMap<String, usize>,
    mocks: Vec<ScopeMock>,
    mock_indexes: HashMap<String, usize>,
    mocks_by_generated_name: HashMap<String, usize>,
}

/// Graph nodes in dependency-first order, built by depth-first traversal.
struct ScopeOrder<'a> {
    graph: &'a ScopeGraph,
    visited: HashSet<ScopeNode>,
    ordered: Vec<ScopeNode>,
}

impl ScopeOrder<'_> {
    fn visit_tokens(&mut self, tokens: &[String]) {
        for token in tokens {
            if let Some(node) = self.graph.node(token) {
                self.visit(node);
            }
        }
    }

    fn visit(&mut self, node: ScopeNode) {
        if !self.visited.insert(node) {
            return;
        }
        let graph = self.graph;
        self.visit_tokens(graph.tokens(node));
        self.ordered.push(node);
    }
}

impl ScopeGraph {
    /// Tokenize every helper body and authored mock body of one test.
    pub(crate) fn new(fixtures: &TestFixtures, patterns: &SqlTestPatterns) -> Self {
        let mock_groups: [(&str, &BTreeMap<String, String>); 4] = [
            (REF_PREFIX, &fixtures.mock_refs),
            (SOURCE_PREFIX, &fixtures.mock_sources),
            (SEED_PREFIX, &fixtures.mock_seeds),
            (DBT_REF_PREFIX, &fixtures.mock_dbt_refs),
        ];
        let mut mocks: Vec<ScopeMock> = Vec::new();
        for (prefix, group) in mock_groups {
            for (name, body) in group {
                mocks.push(ScopeMock {
                    generated_name: format!("{prefix}{name}"),
                    mock_name: name.clone(),
                    sql: body.clone(),
                    tokens: identifier_tokens(body, patterns),
                });
            }
        }
        Self {
            helpers: fixtures
                .helpers
                .iter()
                .map(|cte| (cte.name.clone(), cte.sql_body.clone()))
                .collect(),
            helper_tokens: fixtures
                .helpers
                .iter()
                .map(|cte| identifier_tokens(&cte.sql_body, patterns))
                .collect(),
            helper_indexes: fixtures
                .helpers
                .iter()
                .enumerate()
                .map(|(index, cte)| (cte.name.to_ascii_lowercase(), index))
                .collect(),
            mock_indexes: mocks
                .iter()
                .enumerate()
                .map(|(index, mock)| (mock.generated_name.to_ascii_lowercase(), index))
                .collect(),
            mocks_by_generated_name: mocks
                .iter()
                .enumerate()
                .map(|(index, mock)| (mock.generated_name.clone(), index))
                .collect(),
            mocks,
        }
    }

    fn node(&self, token: &str) -> Option<ScopeNode> {
        self.helper_indexes
            .get(token)
            .map(|index| ScopeNode::Helper(*index))
            .or_else(|| {
                self.mock_indexes
                    .get(token)
                    .map(|index| ScopeNode::Mock(*index))
            })
    }

    fn tokens(&self, node: ScopeNode) -> &[String] {
        match node {
            ScopeNode::Helper(index) => &self.helper_tokens[index],
            ScopeNode::Mock(index) => &self.mocks[index].tokens,
        }
    }

    fn closure(&self, tokens: &[String]) -> Vec<ScopeNode> {
        let mut order = ScopeOrder {
            graph: self,
            visited: HashSet::new(),
            ordered: Vec::new(),
        };
        order.visit_tokens(tokens);
        order.ordered
    }

    /// The authored body of one mock, placed as its own top-level CTE.
    pub(crate) fn mock_sql(&self, generated_name: &str) -> Option<&str> {
        self.mocks_by_generated_name
            .get(generated_name)
            .map(|index| self.mocks[*index].sql.as_str())
    }

    /// One mock inlined in model scope, carrying the helpers it reads so no model CTE shadows them.
    pub(crate) fn inlined_mock_sql(&self, generated_name: &str) -> Option<String> {
        let mock = &self.mocks[*self.mocks_by_generated_name.get(generated_name)?];
        Some(parenthesized_sql(
            &self.with_read_helpers(&mock.sql, &mock.tokens),
        ))
    }

    /// A table-function fixture inlined into model SQL, with the helpers it reads.
    pub(crate) fn inlined_fixture_sql(&self, sql: &str, patterns: &SqlTestPatterns) -> String {
        parenthesized_sql(&self.with_read_helpers(sql, &identifier_tokens(sql, patterns)))
    }

    fn with_read_helpers(&self, sql: &str, tokens: &[String]) -> String {
        let helpers: Vec<(String, String)> = self
            .closure(tokens)
            .into_iter()
            .filter_map(|node| match node {
                ScopeNode::Helper(index) => Some(self.helpers[index].clone()),
                ScopeNode::Mock(_) => None,
            })
            .collect();
        with_leading_ctes(&helpers, sql)
    }

    /// Helpers and mocks one top-level mock reads, transitively and dependencies first.
    pub(crate) fn mock_dependencies(&self, generated_name: &str) -> Vec<ScopeDependency<'_>> {
        let Some(root) = self.mocks_by_generated_name.get(generated_name).copied() else {
            return Vec::new();
        };
        self.dependencies(self.closure(&self.mocks[root].tokens), root)
    }

    /// Top-level CTEs an inlined mock needs: the mocks it reads and everything they read.
    pub(crate) fn inlined_mock_dependencies(
        &self,
        generated_name: &str,
    ) -> Vec<ScopeDependency<'_>> {
        let Some(root) = self.mocks_by_generated_name.get(generated_name).copied() else {
            return Vec::new();
        };
        let mut order = ScopeOrder {
            graph: self,
            visited: HashSet::new(),
            ordered: Vec::new(),
        };
        for node in self.closure(&self.mocks[root].tokens) {
            if matches!(node, ScopeNode::Mock(index) if index != root) {
                order.visit(node);
            }
        }
        self.dependencies(order.ordered, root)
    }

    fn dependencies(&self, nodes: Vec<ScopeNode>, root: usize) -> Vec<ScopeDependency<'_>> {
        nodes
            .into_iter()
            .filter_map(|node| match node {
                ScopeNode::Mock(index) if index == root => None,
                ScopeNode::Mock(index) => Some(ScopeDependency {
                    generated_name: &self.mocks[index].generated_name,
                    mock_name: Some(&self.mocks[index].mock_name),
                    sql: &self.mocks[index].sql,
                }),
                ScopeNode::Helper(index) => Some(ScopeDependency {
                    generated_name: &self.helpers[index].0,
                    mock_name: None,
                    sql: &self.helpers[index].1,
                }),
            })
            .collect()
    }
}

/// Return the helper and mock CTEs `sql` reads, transitively and dependencies first.
pub(crate) fn helper_scope_ctes(
    sql: &str,
    fixtures: &TestFixtures,
    patterns: &SqlTestPatterns,
    file_label: &str,
) -> Result<HelperScope, String> {
    let mut scope = HelperScope {
        ctes: Vec::new(),
        reached_mocks: HashSet::new(),
    };
    if fixtures.helpers.is_empty() && fixtures.scope.mocks.is_empty() {
        return Ok(scope);
    }
    for node in fixtures.scope.closure(&identifier_tokens(sql, patterns)) {
        match node {
            ScopeNode::Mock(index) => {
                let mock = &fixtures.scope.mocks[index];
                scope.reached_mocks.insert(mock.mock_name.clone());
                scope
                    .ctes
                    .push((mock.generated_name.clone(), mock.sql.clone()));
            }
            ScopeNode::Helper(index) => {
                let helper = &fixtures.helpers[index];
                if is_generated_cte_name(&helper.name) {
                    return Err(compile_error(&format!(
                        "SQL test '{file_label}' defines CTE '{}', which conflicts with the generated CTE",
                        helper.name
                    )));
                }
                scope
                    .ctes
                    .push((helper.name.clone(), helper.sql_body.clone()));
            }
        }
    }
    Ok(scope)
}

/// Append scoped CTEs after a step's generated CTEs, keeping one definition per name.
pub(crate) fn merged_scoped_ctes(
    mut lifted: Vec<(String, String)>,
    scoped: Vec<(String, String)>,
    file_label: &str,
) -> Result<Vec<(String, String)>, String> {
    for (name, sql) in scoped {
        match lifted
            .iter()
            .find(|(existing, _)| existing.eq_ignore_ascii_case(&name))
        {
            Some((_, existing_sql)) if *existing_sql == sql => {}
            Some(_) => {
                return Err(compile_error(&format!(
                    "SQL test '{file_label}' defines CTE '{name}', which conflicts with the generated CTE"
                )));
            }
            None => lifted.push((name, sql)),
        }
    }
    Ok(lifted)
}

/// Names the comparison renderer generates, which a scoped helper CTE must not shadow.
fn is_generated_cte_name(name: &str) -> bool {
    let lowered = name.to_ascii_lowercase();
    lowered == SQL_TEST_ACTUAL_CTE
        || lowered == SQL_TEST_EXPECTED_CTE
        || lowered.starts_with(SQL_TEST_ACTUAL_CTE_PREFIX)
}

/// Distinct lowercase identifiers outside strings and comments, in first-appearance order.
fn identifier_tokens(sql: &str, patterns: &SqlTestPatterns) -> Vec<String> {
    let protected = protected_ranges(&patterns.lexical, sql);
    let mut seen: HashSet<String> = HashSet::new();
    let mut tokens: Vec<String> = Vec::new();
    let mut push = |token: &str| {
        let lowered = token.to_ascii_lowercase();
        if seen.insert(lowered.clone()) {
            tokens.push(lowered);
        }
    };
    for found in patterns.identifier.find_iter(sql) {
        let preceded_by_identifier = sql[..found.start()]
            .chars()
            .next_back()
            .is_some_and(|character| character.is_alphanumeric() || character == '_');
        if !preceded_by_identifier && !in_protected_range(found.start(), &protected) {
            push(found.as_str());
        }
    }
    for (start, end) in protected {
        let text = &sql[start..end];
        if let Some(quote) = text
            .chars()
            .next()
            .filter(|quote| matches!(quote, '"' | '`'))
            && text.len() >= QUOTED_IDENTIFIER_DELIMITER_BYTES
            && text.ends_with(quote)
        {
            push(&text[1..text.len() - 1]);
        }
    }
    tokens
}
