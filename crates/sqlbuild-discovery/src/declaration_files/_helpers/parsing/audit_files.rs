//! Python's `parse_sql_audit_file`: split `AUDIT(...)` blocks and check each header and body.

use crate::_helpers::statement_headers::{StatementHeader, parse_statement_header};
use crate::declaration_files::_helpers::checks::python_values::{
    PythonType, WordRules, failure, get, non_empty_str, python_str, python_type,
};
use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::declaration_files::_helpers::parsing::audit_text::{AuditText, chars, text};
use crate::declaration_files::models::{AuditBlock, AuditFile, DeclarationFileOptions};
use crate::models::FailureKind;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::python_cleandoc::python_cleandoc;
use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

const AUDIT_KEYWORD: &str = "AUDIT";
const STRING_KEYS: [&str; 7] = [
    "name",
    "severity",
    "run_scope",
    "evaluation",
    "value",
    "sample_count",
    "sample_unit",
];
const BOOLEAN_KEYS: [&str; 2] = ["always_run", "sql_analysis"];
const MEASUREMENT_ONLY_KEYS: [&str; 5] = [
    "value",
    "sample_count",
    "sample_unit",
    "thresholds",
    "minimum_samples",
];
const VIOLATIONS: &str = "violations";
const MEASUREMENT: &str = "measurement";

/// The file, its parsing options and the code points of the text being parsed.
struct AuditParse<'a> {
    file_path: &'a str,
    options: &'a DeclarationFileOptions,
}

fn audit_failure(message: String) -> ParseStop {
    failure(FailureKind::SqlAudit, message)
}

pub(crate) fn parse_audit_file(
    file_path: &str,
    contents: String,
    options: &DeclarationFileOptions,
) -> Result<AuditFile, ParseStop> {
    let parse = AuditParse { file_path, options };
    let content_chars: Vec<char> = chars(&contents);
    let content_text = AuditText {
        chars: &content_chars,
        python: options.python,
    };
    let starts: Vec<usize> = content_text.top_level_keywords(AUDIT_KEYWORD);
    let leading: String = starts
        .first()
        .map_or_else(String::new, |first| text(&content_chars[..*first]));
    if starts.is_empty() || !python_strip(&leading).is_empty() {
        return Err(audit_failure(format!(
            "SQL audit '{file_path}' must start with an AUDIT() header as the first \
             non-whitespace content"
        )));
    }
    let mut blocks: Vec<AuditBlock> = Vec::with_capacity(starts.len());
    for (offset, start) in starts.iter().enumerate() {
        let end: usize = starts
            .get(offset + 1)
            .copied()
            .unwrap_or(content_chars.len());
        let raw_block: String = python_strip(&text(&content_chars[*start..end])).to_owned();
        let block_line: usize = content_chars[..*start]
            .iter()
            .filter(|character| **character == '\n')
            .count()
            + 1;
        blocks.push(parse.block(&raw_block, block_line, offset + 1)?);
    }
    validate_audit_names(file_path, &blocks)?;
    Ok(AuditFile { contents, blocks })
}

impl AuditParse<'_> {
    fn text<'a>(&self, chars: &'a [char]) -> AuditText<'a> {
        AuditText {
            chars,
            python: self.options.python,
        }
    }

    fn block(
        &self,
        raw_block: &str,
        block_line: usize,
        audit_index: usize,
    ) -> Result<AuditBlock, ParseStop> {
        let file_path: &str = self.file_path;
        let block_chars: Vec<char> = chars(raw_block);
        let block = self.text(&block_chars);
        let open_index: usize = self.keyword_open_paren(&block, 0, AUDIT_KEYWORD)?;
        let close_index: usize = block
            .matching_parenthesis(open_index)
            .ok_or_else(|| audit_failure(format!("Unclosed AUDIT(...) block in '{file_path}'")))?;
        let body_start: usize =
            self.consume_delimiter(&block, close_index + 1, "AUDIT(...) header")?;
        let header: String = text(&block_chars[open_index + 1..close_index]);
        let header_line: usize = block_line
            + block_chars[..=open_index]
                .iter()
                .filter(|character| **character == '\n')
                .count();
        let header_values: Vec<(String, AuthoredValue)> = self.header(&header, header_line)?;
        let evaluation_mode: &'static str =
            evaluation_mode(&header_values, file_path, self.options.python)?;
        let body: &[char] = &block_chars[body_start..];
        let mut measure_sql: Option<String> = None;
        let mut evidence_sql: Option<String> = None;
        let sql_body: String = if evaluation_mode == MEASUREMENT {
            let (measure, evidence) = self.measurement_body(body)?;
            measure_sql = Some(measure.clone());
            evidence_sql = evidence;
            measure
        } else {
            let sql_body: String = python_cleandoc(self.options.python, &text(body));
            if sql_body.is_empty() {
                return Err(audit_failure(format!(
                    "SQL audit '{file_path}' must define SQL after AUDIT(...)"
                )));
            }
            let sql_chars: Vec<char> = chars(&sql_body);
            let sql = self.text(&sql_chars);
            let code_start: usize = sql.skip_space_and_comments(0);
            if sql.top_level_keywords("MEASURE").contains(&code_start)
                || sql.top_level_keywords("EVIDENCE").contains(&code_start)
            {
                return Err(audit_failure(format!(
                    "Violation audit '{file_path}' must use a bare SELECT body, not \
                     MEASURE/EVIDENCE"
                )));
            }
            sql_body
        };
        let name: Option<String> = match get(&header_values, "name") {
            Some(value) => python_str(
                value,
                WordRules {
                    python: self.options.python,
                    file_path,
                },
            )?
            .map(str::to_owned),
            None => None,
        };
        Ok(AuditBlock {
            audit_index,
            header_values,
            sql_body,
            name,
            evaluation_mode,
            measure_sql,
            evidence_sql,
        })
    }

    fn header(
        &self,
        header: &str,
        header_line: usize,
    ) -> Result<Vec<(String, AuthoredValue)>, ParseStop> {
        let file_path: &str = self.file_path;
        let values: Vec<(String, AuthoredValue)> = parse_statement_header(
            &StatementHeader {
                kind: FailureKind::SqlAudit,
                statement_name: AUDIT_KEYWORD,
                statement: "AUDIT()",
                file_path,
                supported_keys: &self.options.audit_keys,
                python: self.options.python,
            },
            header,
            header_line,
        )?;
        for key in STRING_KEYS {
            if let Some(value) = get(&values, key)
                && non_empty_str(
                    value,
                    WordRules {
                        python: self.options.python,
                        file_path,
                    },
                )?
                .is_none()
            {
                return Err(audit_failure(format!(
                    "AUDIT() {key} in '{file_path}' must be a non-empty string"
                )));
            }
        }
        for key in BOOLEAN_KEYS {
            if let Some(value) = get(&values, key)
                && python_type(
                    value,
                    WordRules {
                        python: self.options.python,
                        file_path,
                    },
                )? != PythonType::Bool
            {
                return Err(audit_failure(format!(
                    "AUDIT() {key} in '{file_path}' must be a boolean"
                )));
            }
        }
        Ok(values)
    }

    /// `_keyword_open_paren` for the keyword at the first code after `start`.
    fn keyword_open_paren(
        &self,
        text: &AuditText<'_>,
        start: usize,
        keyword: &str,
    ) -> Result<usize, ParseStop> {
        let missing = || {
            audit_failure(format!(
                "SQL audit '{}' must start with {keyword}(...)",
                self.file_path
            ))
        };
        let keyword_start: usize = text.skip_space_and_comments(start);
        if !keyword_at_slice_start(text, keyword, keyword_start, start) {
            return Err(missing());
        }
        let position: usize = text.skip_space_and_comments(keyword_start + keyword.len());
        if text.chars.get(position) != Some(&'(') {
            return Err(missing());
        }
        Ok(position)
    }

    /// `_consume_delimiter`: the position after the `;` that must follow `start`.
    fn consume_delimiter(
        &self,
        text: &AuditText<'_>,
        start: usize,
        label: &str,
    ) -> Result<usize, ParseStop> {
        let position: usize = text.skip_space_and_comments(start);
        if text.chars.get(position) != Some(&';') {
            return Err(audit_failure(format!(
                "{label} in '{}' must end with `);`",
                self.file_path
            )));
        }
        Ok(position + 1)
    }

    /// `_parse_measurement_body`: one `MEASURE(...)` block and an optional `EVIDENCE(...)` block.
    fn measurement_body(&self, body: &[char]) -> Result<(String, Option<String>), ParseStop> {
        let file_path: &str = self.file_path;
        let text = self.text(body);
        let mut position: usize = text.skip_space_and_comments(0);
        if !text.keyword_at("MEASURE", position) {
            return Err(audit_failure(format!(
                "Measurement audit '{file_path}' must define exactly one MEASURE(...) block"
            )));
        }
        let (measure, end) = self.delimited_query(&text, position, "MEASURE")?;
        position = text.skip_space_and_comments(end);
        let mut evidence: Option<String> = None;
        if text.keyword_at("EVIDENCE", position) {
            let (query, end) = self.delimited_query(&text, position, "EVIDENCE")?;
            evidence = Some(query);
            position = text.skip_space_and_comments(end);
        }
        if position != text.len() {
            let label: &str =
                if text.keyword_at("MEASURE", position) || text.keyword_at("EVIDENCE", position) {
                    "duplicate MEASURE/EVIDENCE block"
                } else {
                    "bare SQL outside MEASURE/EVIDENCE blocks"
                };
            return Err(audit_failure(format!(
                "Measurement audit '{file_path}' has {label}"
            )));
        }
        Ok((measure, evidence))
    }

    /// `_extract_delimited_query` for a keyword already found at `position`.
    fn delimited_query(
        &self,
        scan: &AuditText<'_>,
        position: usize,
        keyword: &str,
    ) -> Result<(String, usize), ParseStop> {
        let file_path: &str = self.file_path;
        let open_index: usize = self.keyword_open_paren(scan, position, keyword)?;
        let close_index: usize = scan.matching_parenthesis(open_index).ok_or_else(|| {
            audit_failure(format!("Unclosed {keyword}(...) block in '{file_path}'"))
        })?;
        let query: String = python_cleandoc(
            self.options.python,
            &text(&scan.chars[open_index + 1..close_index]),
        );
        self.validate_single_query(&query, keyword)?;
        let end: usize =
            self.consume_delimiter(scan, close_index + 1, &format!("{keyword}(...) block"))?;
        Ok((query, end))
    }

    /// `_validate_single_query`: one `SELECT` or `WITH` query, optionally ending with `;`.
    fn validate_single_query(&self, query: &str, label: &str) -> Result<(), ParseStop> {
        let file_path: &str = self.file_path;
        let one_select = || {
            audit_failure(format!(
                "{label}(...) in '{file_path}' must contain one SELECT query"
            ))
        };
        if query.is_empty() {
            return Err(one_select());
        }
        let query_chars: Vec<char> = chars(query);
        let query_text = self.text(&query_chars);
        let start: usize = query_text.skip_space_and_comments(0);
        if !(query_text.keyword_at("SELECT", start) || query_text.keyword_at("WITH", start)) {
            return Err(one_select());
        }
        let semicolons: Vec<usize> = query_text.top_level_semicolons();
        if let Some(first) = semicolons.first()
            && (semicolons.len() > 1
                || query_chars[first + 1..]
                    .iter()
                    .any(|character| !is_python_space(*character)))
        {
            return Err(audit_failure(format!(
                "{label}(...) in '{file_path}' must contain exactly one query"
            )));
        }
        Ok(())
    }
}

/// `_keyword_at(text[start:], keyword, position - start)`: the slice hides what precedes it.
fn keyword_at_slice_start(
    text: &AuditText<'_>,
    keyword: &str,
    position: usize,
    slice_start: usize,
) -> bool {
    if position == slice_start {
        let slice = AuditText {
            chars: &text.chars[slice_start..],
            python: text.python,
        };
        return slice.keyword_at(keyword, 0);
    }
    text.keyword_at(keyword, position)
}

fn evaluation_mode(
    header_values: &[(String, AuthoredValue)],
    file_path: &str,
    python: PythonText,
) -> Result<&'static str, ParseStop> {
    let mode: &str = match get(header_values, "evaluation") {
        Some(value) => python_str(value, WordRules { python, file_path })?.unwrap_or_default(),
        None => VIOLATIONS,
    };
    let mode: &'static str = match mode {
        VIOLATIONS => VIOLATIONS,
        MEASUREMENT => MEASUREMENT,
        _ => {
            return Err(audit_failure(format!(
                "AUDIT() evaluation in '{file_path}' must be one of: violations, measurement"
            )));
        }
    };
    if mode == VIOLATIONS {
        let invalid: Vec<&str> = MEASUREMENT_ONLY_KEYS
            .into_iter()
            .filter(|key| get(header_values, key).is_some())
            .collect();
        if !invalid.is_empty() {
            return Err(audit_failure(format!(
                "Violation audit '{file_path}' must not define measurement keys: {}",
                invalid.join(", ")
            )));
        }
    } else if get(header_values, "value").is_none() {
        return Err(audit_failure(format!(
            "Measurement audit '{file_path}' must define `value`"
        )));
    }
    Ok(mode)
}

fn validate_audit_names(file_path: &str, blocks: &[AuditBlock]) -> Result<(), ParseStop> {
    if blocks.len() <= 1 {
        return Ok(());
    }
    let unnamed: Vec<String> = blocks
        .iter()
        .filter(|block| block.name.is_none())
        .map(|block| block.audit_index.to_string())
        .collect();
    if !unnamed.is_empty() {
        return Err(audit_failure(format!(
            "SQL audit '{file_path}' contains multiple AUDIT blocks; every block must define a \
             unique `name`. Missing names for blocks: {}",
            unnamed.join(", ")
        )));
    }
    let mut seen: Vec<&str> = Vec::with_capacity(blocks.len());
    for block in blocks {
        let name: &str = block.name.as_deref().unwrap_or_default();
        if seen.contains(&name) {
            return Err(audit_failure(format!(
                "SQL audit '{file_path}' defines duplicate AUDIT() name '{name}'"
            )));
        }
        seen.push(name);
    }
    Ok(())
}
