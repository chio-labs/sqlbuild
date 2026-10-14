//! Fixture block eligibility, extraction, and ordered text replacement.

use regex::Regex;
use sqlbuild_scopes::relationship_names::main::top_level_ctes::scan_top_level_ctes;
use sqlbuild_scopes::relationship_names::models::{RelationshipSource, TopLevelCtes};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;
use std::collections::HashMap;
use std::sync::LazyLock;

use crate::lint_text::_helpers::fixture_formatting::simplify_fixture_nulls;
use crate::lint_text::models::{FixtureFormatBlock, FixtureFormatRelation};

static CANDIDATE: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(r"(?i)(?:CAST\s*\(\s*NULL\s+AS\b|NULL\s*::)"));

pub(crate) fn format(
    (contents, label): (&str, &str),
    blocks: &[FixtureFormatBlock],
    relations: &HashMap<String, FixtureFormatRelation>,
    syntax: &LexicalSyntax,
) -> Result<Option<String>, regex::Error> {
    let candidate = CANDIDATE.as_ref().map_err(Clone::clone)?;
    let mut result = contents.to_owned();
    let mut changed = false;
    for block in blocks {
        if !block.model_mode || block.sql_body.contains('@') || !candidate.is_match(&block.sql_body)
        {
            continue;
        }
        let TopLevelCtes::Scanned(ctes) =
            scan_top_level_ctes(&block.sql_body, label, RelationshipSource::Test, syntax)
        else {
            continue;
        };
        let mut replacements: Vec<(String, String)> = Vec::new();
        for (name, body) in ctes {
            let Some(relation) = relations.get(&name) else {
                continue;
            };
            let replacement = simplify_fixture_nulls(&body, &relation.columns)?;
            if replacement != body {
                replacements.push((body, replacement));
            }
        }
        let mut fixed = block.sql_body.clone();
        for (original, replacement) in replacements {
            if fixed.matches(&original).count() == 1 {
                fixed = fixed.replacen(&original, &replacement, 1);
            }
        }
        if fixed != block.sql_body {
            result = result.replacen(&block.sql_body, &fixed, 1);
            changed = true;
        }
    }
    Ok(changed.then_some(result))
}
