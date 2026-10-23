//! Python's `parse_function_sql`: a `FUNCTION(...);` header and the SQL body after it.

use crate::_helpers::header_syntax::header_position;
use crate::_helpers::statement_headers::{StatementHeader, parse_statement_header};
use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::declaration_files::models::{DeclarationFileOptions, FunctionFile};
use crate::models::{DiscoveryFailure, FailureKind};
use sqlbuild_sqltext::compiler::main::statement_header_matching::match_statement_header;

const FUNCTION_KEYWORD: &str = "FUNCTION";

pub(crate) fn parse_function_file(
    file_path: &str,
    contents: String,
    options: &DeclarationFileOptions,
) -> Result<FunctionFile, ParseStop> {
    let Some((header_start, header_end, sql_start)) =
        match_statement_header(&contents, 0, FUNCTION_KEYWORD)
    else {
        return Err(ParseStop::Failed(DiscoveryFailure::new(
            FailureKind::ModelSql,
            format!(
                "SQL function '{file_path}' must start with a FUNCTION(...) header as the first \
                 non-whitespace content"
            ),
        )));
    };
    let header_values = parse_statement_header(
        &StatementHeader {
            kind: FailureKind::ModelSql,
            statement_name: FUNCTION_KEYWORD,
            statement: "FUNCTION()",
            file_path,
            supported_keys: &options.function_keys,
        },
        &contents[header_start..header_end],
        header_position(&contents, header_start),
    )?;
    let body_sql: String = str::trim(&contents[sql_start..]).to_owned();
    if body_sql.is_empty() {
        return Err(ParseStop::Failed(DiscoveryFailure::new(
            FailureKind::ModelSql,
            format!("SQL function '{file_path}' must contain SQL after FUNCTION(...)"),
        )));
    }
    Ok(FunctionFile {
        contents,
        header_values,
        body_sql,
    })
}
