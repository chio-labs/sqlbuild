//! Helper CTEs placed in scope for SQL-test expected and assertion queries.

use std::collections::{BTreeMap, HashMap, HashSet};

use crate::compiler::_helpers::sql_tests::planning::{
    DBT_REF_PREFIX, REF_PREFIX, SEED_PREFIX, SOURCE_PREFIX, SqlTestPatterns, TestFixtures,
    compile_error, in_protected_range, mock_cte_sql, protected_ranges,
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

/// Helper indexes in dependency-first order, built by depth-first traversal.
struct HelperOrder<'a> {
    indexes: HashMap<String, usize>,
    tokens: &'a [Vec<String>],
    visited: HashSet<usize>,
    ordered: Vec<usize>,
}

impl HelperOrder<'_> {
    fn visit(&mut self, index: usize) {
        if !self.visited.insert(index) {
            return;
        }
        for token in &self.tokens[index] {
            if let Some(dependency) = self.indexes.get(token).copied()
                && dependency != index
            {
                self.visit(dependency);
            }
        }
        self.ordered.push(index);
    }
}

/// Return mocks read by name, then helpers `sql` references transitively, dependencies first.
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
    if fixtures.helpers.is_empty() {
        return Ok(scope);
    }
    let helper_tokens: Vec<Vec<String>> = fixtures
        .helpers
        .iter()
        .map(|cte| identifier_tokens(&cte.sql_body, patterns))
        .collect();
    let mut order = HelperOrder {
        indexes: fixtures
            .helpers
            .iter()
            .enumerate()
            .map(|(index, cte)| (cte.name.to_ascii_lowercase(), index))
            .collect(),
        tokens: &helper_tokens,
        visited: HashSet::new(),
        ordered: Vec::new(),
    };
    for token in identifier_tokens(sql, patterns) {
        if let Some(index) = order.indexes.get(&token).copied() {
            order.visit(index);
        }
    }
    let ordered = order.ordered;
    let mock_groups: [(&str, &BTreeMap<String, String>); 4] = [
        (REF_PREFIX, &fixtures.mock_refs),
        (SOURCE_PREFIX, &fixtures.mock_sources),
        (SEED_PREFIX, &fixtures.mock_seeds),
        (DBT_REF_PREFIX, &fixtures.mock_dbt_refs),
    ];
    let mut emitted_mocks: HashSet<String> = HashSet::new();
    for token in ordered.iter().flat_map(|index| &helper_tokens[*index]) {
        for (prefix, mocks) in mock_groups {
            let Some(referenced) = token.strip_prefix(prefix) else {
                continue;
            };
            let Some((mock_name, mock_body)) = mocks
                .iter()
                .find(|(name, _)| name.eq_ignore_ascii_case(referenced))
            else {
                continue;
            };
            let generated_name = format!("{prefix}{mock_name}");
            if emitted_mocks.insert(generated_name.clone()) {
                scope.reached_mocks.insert(mock_name.clone());
                scope
                    .ctes
                    .push((generated_name, mock_cte_sql(mock_body, &fixtures.helpers)));
            }
        }
    }
    for index in ordered {
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
    let protected = protected_ranges(&patterns.protected, sql);
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
