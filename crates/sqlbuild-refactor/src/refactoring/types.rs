//! Callback and alias types shared by refactoring planning and its bindings.

use sqlbuild_core::text::errors::TextDecodeError;

use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::DeclarationPlacement;

/// The shared scope placement once every `(model, destination)` move is applied together.
pub type DeclarationMoveHost<'a> =
    dyn Fn(&[(String, String)]) -> Result<DeclarationPlacement, RefactorError> + 'a;

/// Used scoped declarations a `(test path, destination)` move would rebind; `None` if unknown.
pub type UnitTestScopeHost<'a> =
    dyn Fn(&str, &str) -> Result<Option<Vec<String>>, RefactorError> + 'a;

/// Original texts keyed by original path, in plan order.
pub type Originals = Vec<(String, String)>;

/// One project file's POSIX path and its text, or why it is not UTF-8.
pub type ProjectText = (String, Result<String, TextDecodeError>);

/// One physical column: `(name, type)`.
pub type PhysicalColumn = (String, String);

/// Replace lines `start..end` with new lines, as contract adoption's YAML source edit plans it.
pub type LineEdit = (usize, usize, Vec<String>);
