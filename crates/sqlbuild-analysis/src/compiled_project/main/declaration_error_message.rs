use crate::compiled_project::_helpers::declaration_errors;
use crate::compiled_project::errors::DeclarationError;

/// The message the attachment raises for one enum or constant expansion error.
pub fn declaration_error_message(error: &DeclarationError, consumer: &str) -> String {
    match error {
        DeclarationError::Unknown {
            kind,
            name,
            visible,
        } => declaration_errors::unknown_declaration(kind, name, consumer, visible),
        DeclarationError::UnknownMember {
            name,
            member,
            members,
        } => declaration_errors::unknown_member(name, member, consumer, members),
        DeclarationError::Inaccessible { kind, name, record } => {
            declaration_errors::inaccessible(kind, name, consumer, record)
        }
        DeclarationError::ScanStop(code) => declaration_errors::scan_stop(*code, consumer),
    }
}
