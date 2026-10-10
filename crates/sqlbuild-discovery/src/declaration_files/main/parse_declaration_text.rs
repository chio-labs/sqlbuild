//! Parse in-memory declaration file contents as discovery parses a file of one kind.

use crate::_helpers::pool::on_discovery_pool;
use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::declaration_files::_helpers::parsing::audit_files::parse_audit_file;
use crate::declaration_files::_helpers::parsing::constant_files::parse_constant_file;
use crate::declaration_files::_helpers::parsing::enum_files::parse_enum_file;
use crate::declaration_files::_helpers::parsing::function_files::parse_function_file;
use crate::declaration_files::_helpers::parsing::hook_files::parse_hook_file;
use crate::declaration_files::_helpers::parsing::schema_files::parse_schema_file;
use crate::declaration_files::models::{
    CollectionKind, DeclarationFileOptions, ParsedDeclarationText,
};
use crate::models::FileOutcome;

/// `contents` parsed on the discovery pool as a `kind` file; `None` for seeds and macros.
pub fn parse_declaration_text(
    kind: CollectionKind,
    (file_path, hook_name): (&str, &str),
    contents: String,
    options: &DeclarationFileOptions,
) -> Option<FileOutcome<ParsedDeclarationText>> {
    on_discovery_pool(|| parse_text(kind, (file_path, hook_name), contents, options))
}

fn parse_text(
    kind: CollectionKind,
    (file_path, hook_name): (&str, &str),
    contents: String,
    options: &DeclarationFileOptions,
) -> Option<FileOutcome<ParsedDeclarationText>> {
    let parsed: Result<ParsedDeclarationText, ParseStop> = match kind {
        CollectionKind::Enums => {
            parse_enum_file(file_path, contents, options.python).map(ParsedDeclarationText::Enum)
        }
        CollectionKind::Constants => parse_constant_file(file_path, contents, options.python)
            .map(ParsedDeclarationText::Constant),
        CollectionKind::ModelSchemas => parse_schema_file(file_path, contents, options.python)
            .map(ParsedDeclarationText::ModelSchema),
        CollectionKind::SqlFunctions => parse_function_file(file_path, contents, options)
            .map(ParsedDeclarationText::SqlFunction),
        CollectionKind::SqlHooks => parse_hook_file(file_path, hook_name, contents, options)
            .map(ParsedDeclarationText::SqlHook),
        CollectionKind::Audits => {
            parse_audit_file(file_path, contents, options).map(ParsedDeclarationText::Audit)
        }
        CollectionKind::Seeds | CollectionKind::Macros => return None,
    };
    Some(match parsed {
        Ok(parsed) => FileOutcome::Parsed(parsed),
        Err(ParseStop::Failed(failure)) => FileOutcome::Failed(failure),
    })
}
