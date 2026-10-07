//! The header half of Python's `parse_sql_scenario_file`.

use crate::_helpers::statement_headers::{StatementHeader, parse_statement_header};
use crate::models::{DiscoveryFailure, FailureKind};
use crate::sql_tests::models::DiscoveredScenarioFile;
use sqlbuild_core::text::main::python_cleandoc::python_cleandoc;
use sqlbuild_sqltext::compiler::main::statement_header_matching::match_statement_header;

const SCENARIO_KEYWORD: &str = "SCENARIO";
const SCENARIO_STATEMENT: &str = "SCENARIO()";

pub(crate) fn parse_scenario_file(
    file_path: &str,
    contents: String,
    supported_keys: &[String],
) -> Result<DiscoveredScenarioFile, DiscoveryFailure> {
    let Some((header_start, header_end, sql_start)) =
        match_statement_header(&contents, 0, SCENARIO_KEYWORD)
    else {
        return Err(DiscoveryFailure::new(
            FailureKind::SqlScenario,
            format!(
                "SQL scenario '{file_path}' must start with a SCENARIO() header as the first \
                 non-whitespace content"
            ),
        ));
    };
    let header_values = parse_statement_header(
        &StatementHeader {
            kind: FailureKind::SqlScenario,
            statement_name: SCENARIO_KEYWORD,
            statement: SCENARIO_STATEMENT,
            file_path,
            supported_keys,
        },
        &contents[header_start..header_end],
        contents[..header_start].matches('\n').count() + 1,
    )?;
    let sql_body: String = python_cleandoc(&contents[sql_start..]);
    Ok(DiscoveredScenarioFile {
        contents,
        header_values,
        sql_body,
    })
}
