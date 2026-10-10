//! Native column-reference facts for one SQL body, and the edits they imply, as
//! `column_references.py` derives them.

use std::collections::BTreeSet;

use serde::Deserialize;
use serde_json::{Value, json};

use crate::refactoring::_helpers::chars::slice;
use crate::refactoring::_helpers::sql_sites::{
    AnalysisSql, ModelBody, authored_offset, authored_span,
};
use crate::refactoring::_helpers::text_edits::{manual_at, text_edit};
use crate::refactoring::constants::{
    CTE_SCOPE_PREFIX, REF_KIND, ROOT_SCOPE, SEED_KIND, SOURCE_KIND, UNKNOWN_COLUMN_TYPE,
};
use crate::refactoring::models::{
    EditKind, ManualLocation, RefactorError, RefactorFacts, TextEdit,
};

/// The known output columns of every model, source and seed, keyed by `(kind, name)`.
pub(crate) type ResourceColumns = Vec<((String, String), Vec<String>)>;

#[derive(Debug, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ColumnFacts {
    #[serde(default)]
    pub(crate) parsed: bool,
    #[serde(default)]
    references: Vec<ColumnReference>,
    #[serde(default)]
    stars: Vec<ColumnSite>,
    #[serde(default)]
    joins: Vec<ColumnSite>,
    #[serde(default)]
    unresolved: Vec<ColumnSite>,
    #[serde(default)]
    outputs: Vec<OutputColumn>,
    #[serde(default)]
    star_outputs: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Projection {
    alias: Option<String>,
    alias_start: Option<usize>,
    alias_end: Option<usize>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ColumnReference {
    start: usize,
    end: usize,
    name_start: usize,
    name_end: usize,
    scope: String,
    projection: Option<Projection>,
}

#[derive(Debug, Deserialize)]
struct ColumnSite {
    scope: String,
    start: Option<usize>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct OutputColumn {
    scope: String,
    start: Option<usize>,
    end: Option<usize>,
    alias_start: Option<usize>,
    alias_end: Option<usize>,
}

/// Which column of which relations one analysis resolves.
pub(crate) struct ColumnQuery<'a> {
    pub(crate) column: &'a str,
    pub(crate) target_tables: BTreeSet<String>,
    pub(crate) target_ctes: BTreeSet<String>,
    pub(crate) output_scopes: BTreeSet<String>,
}

/// How one analysed SQL body maps onto its file.
pub(crate) enum BodyMapping {
    /// A model's compiled SQL, mapped back through its expansion passes.
    Model(ModelBody),
    /// An authored body that starts at this file offset.
    Authored(usize),
}

/// Where one analysed SQL body lives, and how its offsets map onto the file.
pub(crate) struct BodyContext<'a> {
    pub(crate) path: &'a str,
    pub(crate) contents: &'a [char],
    pub(crate) mapping: BodyMapping,
    pub(crate) fallback_offset: usize,
}

impl BodyContext<'_> {
    fn map_span(&self, start: usize, end: usize) -> Option<(usize, usize)> {
        match &self.mapping {
            BodyMapping::Model(body) => authored_span(body, start, end),
            BodyMapping::Authored(offset) => Some((offset + start, offset + end)),
        }
    }

    fn locate(&self, offset: usize) -> usize {
        match &self.mapping {
            BodyMapping::Model(body) => authored_offset(body, offset).0,
            BodyMapping::Authored(start) => start + offset,
        }
    }

    fn manual(&self, offset: Option<usize>, reason: String) -> ManualLocation {
        manual_at(
            self.path,
            self.contents,
            Some(offset.unwrap_or(self.fallback_offset)),
            reason,
        )
    }

    fn rename_span(&self, span: (usize, usize), new: &str) -> TextEdit {
        let authored = slice(self.contents, span.0, span.1);
        text_edit(
            self.contents,
            span,
            respell(&authored, new),
            EditKind::Column,
            (None, None),
        )
    }
}

/// Edits, manual locations, and root pass-throughs found in one SQL body.
#[derive(Default)]
pub(crate) struct BodyEdits {
    pub(crate) edits: Vec<TextEdit>,
    pub(crate) manual: Vec<ManualLocation>,
    pub(crate) passes_through: bool,
}

impl BodyEdits {
    fn extend(&mut self, other: Self) {
        self.edits.extend(other.edits);
        self.manual.extend(other.manual);
        self.passes_through = self.passes_through || other.passes_through;
    }

    fn manual(location: ManualLocation) -> Self {
        Self {
            manual: vec![location],
            ..Self::default()
        }
    }
}

fn set_columns(columns: &mut ResourceColumns, key: (String, String), names: Vec<String>) {
    match columns.iter_mut().find(|(item, _)| *item == key) {
        Some(entry) => entry.1 = names,
        None => columns.push((key, names)),
    }
}

/// The known output columns of every model, source, and seed.
pub(crate) fn resource_columns(facts: &RefactorFacts) -> ResourceColumns {
    let mut columns: ResourceColumns = Vec::new();
    for model in &facts.models {
        let mut names: Vec<String> = model.inferred_columns.clone();
        for column in model.schema_columns.iter().flatten() {
            if !names.contains(&column.name) {
                names.push(column.name.clone());
            }
        }
        set_columns(
            &mut columns,
            (REF_KIND.to_owned(), model.name.clone()),
            names,
        );
    }
    for source in &facts.sources {
        set_columns(
            &mut columns,
            (SOURCE_KIND.to_owned(), source.name.clone()),
            source.columns.clone(),
        );
    }
    for seed in &facts.seeds {
        set_columns(
            &mut columns,
            (SEED_KIND.to_owned(), seed.name.clone()),
            seed.columns.clone(),
        );
    }
    columns
}

/// The columns of one resource, or none.
pub(crate) fn columns_of<'a>(columns: &'a ResourceColumns, kind: &str, name: &str) -> &'a [String] {
    columns
        .iter()
        .find(|((item_kind, item_name), _)| item_kind == kind && item_name == name)
        .map_or(&[], |(_, names)| names.as_slice())
}

/// Resolve every use of one column of the target relations in one SQL body.
pub(crate) fn analyze_column(
    analysis: &AnalysisSql,
    dialect: &str,
    columns: &ResourceColumns,
    query: &ColumnQuery<'_>,
) -> Result<ColumnFacts, RefactorError> {
    let mut tables: Vec<Value> = Vec::new();
    for ((kind, name), placeholders) in &analysis.tables {
        let known: Vec<Value> = columns_of(columns, kind, name)
            .iter()
            .map(|column| json!({"name": column, "type": UNKNOWN_COLUMN_TYPE}))
            .collect();
        for placeholder in placeholders {
            tables.push(json!({"name": placeholder, "columns": known.clone()}));
        }
    }
    let request = json!({
        "sql": analysis.sql,
        "dialect": dialect,
        "column": query.column,
        "schema": {"strict": false, "tables": tables},
        "target_tables": query.target_tables,
        "target_ctes": query.target_ctes,
        "output_ctes": query.output_scopes,
    });
    let response =
        sqlbuild_analysis::column_references::main::analyze::analyze_json(&request.to_string())
            .map_err(RefactorError::value)?;
    serde_json::from_str(&response).map_err(|error| RefactorError::value(error.to_string()))
}

/// Rename every reference; keep consumer output names unless the root passes it on.
pub(crate) fn consumer_edits(
    facts: &ColumnFacts,
    context: &BodyContext<'_>,
    names: (&str, &str),
    cascade_root: bool,
    root_stars_pass: bool,
) -> BodyEdits {
    let (old, _) = names;
    if !facts.parsed {
        return BodyEdits::manual(context.manual(None, "SQL could not be analysed".to_owned()));
    }
    let mut result = BodyEdits::default();
    for reference in &facts.references {
        result.extend(reference_edits(reference, context, names, cascade_root));
    }
    for star in &facts.stars {
        result.extend(star_edits(star, context, old, root_stars_pass));
    }
    for site in &facts.joins {
        result.extend(finding(
            context,
            site,
            format!("USING or NATURAL join on {old}; rewrite it as an ON condition"),
        ));
    }
    for site in &facts.unresolved {
        result.extend(finding(
            context,
            site,
            format!("cannot tell whether {old} here is the renamed column; qualify it"),
        ));
    }
    result
}

fn reference_edits(
    reference: &ColumnReference,
    context: &BodyContext<'_>,
    names: (&str, &str),
    cascade_root: bool,
) -> BodyEdits {
    let (old, new) = names;
    let Some(name_span) = context.map_span(reference.name_start, reference.name_end) else {
        return BodyEdits::manual(context.manual(
            Some(context.locate(reference.name_start)),
            format!(
                "column {old} is referenced in SQL a macro generates; update the macro call by hand"
            ),
        ));
    };
    let authored_name = slice(context.contents, name_span.0, name_span.1);
    let renamed = context.rename_span(name_span, new);
    let Some(projection) = &reference.projection else {
        return BodyEdits {
            edits: vec![renamed],
            ..BodyEdits::default()
        };
    };
    let same_name_alias = projection
        .alias
        .as_ref()
        .is_some_and(|alias| alias.to_lowercase() == old.to_lowercase());
    if reference.scope == ROOT_SCOPE
        && cascade_root
        && (projection.alias.is_none() || same_name_alias)
    {
        let alias_span = match (
            same_name_alias,
            projection.alias_start,
            projection.alias_end,
        ) {
            (true, Some(start), Some(end)) => context.map_span(start, end),
            _ => None,
        };
        let mut edits = vec![renamed];
        edits.extend(alias_span.map(|span| context.rename_span(span, new)));
        return BodyEdits {
            edits,
            manual: Vec::new(),
            passes_through: true,
        };
    }
    if projection.alias.is_some() {
        return BodyEdits {
            edits: vec![renamed],
            ..BodyEdits::default()
        };
    }
    let Some(end_span) = context.map_span(reference.start, reference.end) else {
        return BodyEdits::manual(context.manual(
            Some(name_span.0),
            format!("column {old} is projected inside a macro call"),
        ));
    };
    let alias = text_edit(
        context.contents,
        (end_span.1, end_span.1),
        format!(" AS {authored_name}"),
        EditKind::Column,
        (Some(String::new()), Some(format!("AS {authored_name}"))),
    );
    BodyEdits {
        edits: vec![renamed, alias],
        ..BodyEdits::default()
    }
}

fn star_edits(
    star: &ColumnSite,
    context: &BodyContext<'_>,
    old: &str,
    root_stars_pass: bool,
) -> BodyEdits {
    if star.scope.starts_with(CTE_SCOPE_PREFIX) {
        return BodyEdits::default();
    }
    if star.scope == ROOT_SCOPE && root_stars_pass {
        return BodyEdits {
            passes_through: true,
            ..BodyEdits::default()
        };
    }
    let reason = if star.scope == ROOT_SCOPE {
        format!(
            "SELECT * passes {old} through, so this model's output column would be renamed too; rerun with --cascade or list the columns"
        )
    } else {
        format!("SELECT * in a subquery passes {old} through; list the columns")
    };
    finding(context, star, reason)
}

fn finding(context: &BodyContext<'_>, site: &ColumnSite, reason: String) -> BodyEdits {
    BodyEdits::manual(context.manual(site.start.map(|start| context.locate(start)), reason))
}

/// Rename the projection that names the column in the given output scopes.
pub(crate) fn output_edits(
    facts: &ColumnFacts,
    context: &BodyContext<'_>,
    scopes: &BTreeSet<String>,
    names: (&str, &str),
) -> BodyEdits {
    let (old, new) = names;
    let mut result = BodyEdits::default();
    let mut found: BTreeSet<&str> = BTreeSet::new();
    for output in &facts.outputs {
        found.insert(&output.scope);
        if let (Some(alias_start), Some(alias_end)) = (output.alias_start, output.alias_end) {
            match context.map_span(alias_start, alias_end) {
                Some(span) => result.edits.push(context.rename_span(span, new)),
                None => result.manual.push(context.manual(
                    Some(context.locate(alias_start)),
                    format!("column {old} is named inside a macro call"),
                )),
            }
            continue;
        }
        let (Some(start), Some(end)) = (output.start, output.end) else {
            continue;
        };
        match context.map_span(start, end) {
            Some(span) => result.edits.push(text_edit(
                context.contents,
                (span.1, span.1),
                format!(" AS {new}"),
                EditKind::Column,
                (Some(String::new()), Some(format!("AS {new}"))),
            )),
            None => result.manual.push(context.manual(
                Some(context.locate(start)),
                format!("column {old} is produced inside a macro call"),
            )),
        }
    }
    for scope in scopes {
        let role = scope_role(scope);
        if !found.contains(role.as_str()) && facts.star_outputs.contains(&role) {
            result.manual.push(context.manual(
                None,
                format!("{old} comes from SELECT * in {scope}; list the columns explicitly"),
            ));
        }
    }
    result
}

fn scope_role(scope: &str) -> String {
    if scope == ROOT_SCOPE {
        scope.to_owned()
    } else {
        format!("{CTE_SCOPE_PREFIX}{scope}")
    }
}

fn respell(authored: &str, name: &str) -> String {
    match authored.chars().next() {
        Some('"') => format!("\"{name}\""),
        Some('`') => format!("`{name}`"),
        Some('[') => format!("[{name}]"),
        _ => name.to_owned(),
    }
}
