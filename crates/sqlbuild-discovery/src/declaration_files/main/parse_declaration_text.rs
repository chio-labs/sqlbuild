//! Parse in-memory declaration file contents as discovery parses a file of one kind.

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

/// `contents` parsed as a `kind` file named `file_path`; `None` for seeds and macros, which have none.
pub fn parse_declaration_text(
    kind: CollectionKind,
    (file_path, hook_name): (&str, &str),
    contents: String,
    options: &DeclarationFileOptions,
) -> Option<FileOutcome<ParsedDeclarationText>> {
    let parsed: Result<ParsedDeclarationText, ParseStop> = match kind {
        CollectionKind::Enums => {
            parse_enum_file(file_path, contents).map(ParsedDeclarationText::Enum)
        }
        CollectionKind::Constants => {
            parse_constant_file(file_path, contents).map(ParsedDeclarationText::Constant)
        }
        CollectionKind::ModelSchemas => {
            parse_schema_file(file_path, contents).map(ParsedDeclarationText::ModelSchema)
        }
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
        Err(ParseStop::Deferred) => FileOutcome::Deferred,
    })
}
