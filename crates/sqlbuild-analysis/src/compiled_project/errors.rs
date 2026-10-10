//! Why an enum or constant reference in a model could not be expanded.

use crate::compiled_project::models::InaccessibleDeclaration;

/// Why an enum or constant reference could not be expanded.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DeclarationError {
    /// `kind` is `enum` or `constant`; `visible` names every declaration of that kind in scope.
    Unknown {
        kind: String,
        name: String,
        visible: Vec<String>,
    },
    UnknownMember {
        name: String,
        member: String,
        members: Vec<String>,
    },
    Inaccessible {
        kind: String,
        name: String,
        record: InaccessibleDeclaration,
    },
    /// The native scan stopped with this code.
    ScanStop(u8),
}
