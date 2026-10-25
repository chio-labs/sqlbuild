use polyglot_sql::Expression;
use std::collections::BTreeSet;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum CallKind {
    Ref,
    Source,
    Other,
}

#[derive(Clone, Debug)]
pub(crate) struct ModelCall {
    pub(crate) kind: CallKind,
    pub(crate) text: String,
    pub(crate) target: Option<String>,
}

/// A model's SQL with dependency calls stubbed by occurrence and normalized as analysis does.
#[derive(Debug)]
pub(crate) struct ModelShape {
    pub(crate) sql: String,
    pub(crate) offsets: Vec<usize>,
    pub(crate) calls: Vec<ModelCall>,
}

/// A comparison's source range and where it starts as an expression, in normalized characters.
#[derive(Clone, Copy, Debug)]
pub(crate) struct ComparisonSpan {
    pub(crate) start: usize,
    pub(crate) end: usize,
    pub(crate) position: Option<usize>,
}

/// The facts built-in model rules read from one query, positions as normalized characters.
#[derive(Debug, Default)]
pub(crate) struct QueryFacts {
    pub(crate) ctes: Vec<CteFacts>,
    pub(crate) body: SetFacts,
    pub(crate) has_order_by: bool,
    pub(crate) has_limit: bool,
    pub(crate) has_fetch: bool,
    pub(crate) has_locks: bool,
}

#[derive(Debug)]
pub(crate) struct CteFacts {
    pub(crate) name: String,
    pub(crate) name_start: Option<usize>,
    pub(crate) columns: Vec<String>,
    pub(crate) query: QueryFacts,
    pub(crate) dependency_calls: Vec<usize>,
}

#[derive(Debug, Default)]
pub(crate) enum SetFacts {
    Select(Box<SelectFacts>),
    Query(Box<QueryFacts>),
    SetOperation {
        by_name: bool,
        left: Box<SetFacts>,
        right: Box<SetFacts>,
    },
    #[default]
    Other,
}

#[derive(Debug, Default)]
pub(crate) struct SelectFacts {
    pub(crate) items: Vec<ItemFacts>,
    pub(crate) from: Vec<RelationFacts>,
    pub(crate) joins: Vec<RelationFacts>,
    pub(crate) filtered: bool,
    pub(crate) comparisons: Vec<ComparisonFacts>,
}

#[derive(Debug)]
pub(crate) enum ItemFacts {
    Star {
        item_start: Option<usize>,
        star_start: Option<usize>,
    },
    Expression(ExpressionItem),
}

#[derive(Debug)]
pub(crate) struct ExpressionItem {
    pub(crate) output_name: Option<String>,
    pub(crate) direct_projection: bool,
    pub(crate) direct_column: Option<String>,
    pub(crate) cast_type: Option<String>,
    pub(crate) start: Option<usize>,
    /// The normalized characters from the expression's first token to its last, alias excluded.
    pub(crate) span: Option<(usize, usize)>,
}

#[derive(Debug)]
pub(crate) enum RelationFacts {
    Table {
        display: String,
        parts: usize,
        start: Option<usize>,
        last: String,
        alias: Option<String>,
    },
    Call {
        kind: CallKind,
        index: Option<usize>,
        alias: Option<String>,
    },
    DynamicPivot,
    Other,
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub(crate) struct ColumnFact {
    pub(crate) name: String,
    pub(crate) qualifier: Option<String>,
}

/// Text read from a model's own SQL when its normalized range is known, else Polyglot's spelling.
#[derive(Debug)]
pub(crate) struct SourceText {
    pub(crate) range: Option<(usize, usize)>,
    pub(crate) generated: String,
}

#[derive(Debug, Default)]
pub(crate) struct ComparisonFacts {
    pub(crate) span: Option<ComparisonSpan>,
    pub(crate) generated_sql: String,
    pub(crate) equality: bool,
    pub(crate) value_list: bool,
    pub(crate) binary: bool,
    pub(crate) output_name: Option<String>,
    pub(crate) columns: BTreeSet<String>,
    pub(crate) string_literals: Vec<SourceText>,
    pub(crate) numeric_literals: Vec<String>,
    pub(crate) modified_columns: BTreeSet<ColumnFact>,
    pub(crate) modified_string_literal: bool,
}

impl QueryFacts {
    /// This query, then every query its top-level CTEs and parenthesized set branches hold.
    pub(crate) fn all_queries(&self) -> Vec<&QueryFacts> {
        fn collect<'a>(query: &'a QueryFacts, values: &mut Vec<&'a QueryFacts>) {
            values.push(query);
            for cte in &query.ctes {
                collect(&cte.query, values);
            }
            collect_set(&query.body, values);
        }
        fn collect_set<'a>(body: &'a SetFacts, values: &mut Vec<&'a QueryFacts>) {
            match body {
                SetFacts::Query(query) => collect(query, values),
                SetFacts::SetOperation { left, right, .. } => {
                    collect_set(left, values);
                    collect_set(right, values);
                }
                SetFacts::Select(_) | SetFacts::Other => {}
            }
        }
        let mut values: Vec<&QueryFacts> = Vec::new();
        collect(self, &mut values);
        values
    }

    /// The plain SELECTs of this query's body: the body itself or every branch of its set operation.
    pub(crate) fn body_selects(&self) -> Vec<&SelectFacts> {
        fn collect<'a>(body: &'a SetFacts, values: &mut Vec<&'a SelectFacts>) {
            match body {
                SetFacts::Select(select) => values.push(select),
                SetFacts::SetOperation { left, right, .. } => {
                    collect(left, values);
                    collect(right, values);
                }
                SetFacts::Query(_) | SetFacts::Other => {}
            }
        }
        let mut values: Vec<&SelectFacts> = Vec::new();
        collect(&self.body, &mut values);
        values
    }

    pub(crate) fn root_select(&self) -> Option<&SelectFacts> {
        match &self.body {
            SetFacts::Select(select) => Some(select),
            _ => None,
        }
    }
}

/// An SQL-test fixture query parsed with Polyglot, with the function-call facts its rules read.
#[derive(Debug)]
pub(crate) struct ParsedFixture {
    pub(crate) statement: Expression,
    pub(crate) calls: Vec<ModelCall>,
    pub(crate) select_function: bool,
    pub(crate) projection_function: bool,
    pub(crate) order_by_function: bool,
    pub(crate) selects: usize,
}

impl ParsedFixture {
    pub(crate) fn select_calls_function(&self) -> bool {
        self.select_function
    }

    pub(crate) fn projection_calls_function(&self) -> bool {
        self.projection_function
    }

    pub(crate) fn order_by_calls_function(&self) -> bool {
        self.order_by_function
    }

    pub(crate) fn query_count(&self) -> usize {
        self.selects
    }
}

/// Character positions of one model's SQL as line and column, with its text by character.
#[derive(Debug)]
pub(crate) struct ModelSource<'a> {
    sql: &'a str,
    bytes: Vec<usize>,
    lines: Vec<usize>,
    offsets: &'a [usize],
    /// The lines of the model file above this SQL.
    line_offset: u64,
}

impl<'a> ModelSource<'a> {
    pub(crate) fn new(sql: &'a str, offsets: &'a [usize], line_offset: u64) -> Self {
        let mut bytes: Vec<usize> = Vec::with_capacity(sql.len() + 1);
        let mut lines: Vec<usize> = vec![0];
        for (character, (byte, value)) in sql.char_indices().enumerate() {
            bytes.push(byte);
            if value == '\n' {
                lines.push(character + 1);
            }
        }
        bytes.push(sql.len());
        Self {
            sql,
            bytes,
            lines,
            offsets,
            line_offset,
        }
    }

    fn original(&self, offset: usize) -> usize {
        self.offsets
            .get(offset)
            .copied()
            .unwrap_or_else(|| self.bytes.len() - 1)
    }

    /// The model's byte range from normalized character `start` to the character before `end`.
    pub(crate) fn byte_range(&self, start: usize, end: usize) -> (usize, usize) {
        let last: usize = self.bytes.len() - 1;
        let first: usize = self.bytes[self.original(start).min(last)];
        let after: usize = self.bytes[(self.original(end.saturating_sub(1)) + 1).min(last)];
        (first, after.max(first))
    }

    /// The 1-based line and column of normalized character `offset`.
    pub(crate) fn line_column(&self, offset: usize) -> (u64, u64) {
        let character = self.original(offset);
        let line = self.lines.partition_point(|start| *start <= character);
        let column = character - self.lines[line - 1] + 1;
        (line as u64 + self.line_offset, column as u64)
    }

    /// The model's own text between normalized characters `start` and `end`.
    pub(crate) fn text(&self, start: usize, end: usize) -> &'a str {
        let last = self.bytes.len() - 1;
        let from = self.bytes[self.original(start).min(last)];
        let to = self.bytes[self.original(end).min(last)];
        self.sql.get(from..to.max(from)).unwrap_or_default()
    }
}
