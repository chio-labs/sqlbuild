//! Callback and alias types shared by refactoring planning and its bindings.

use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::DeclarationPlacement;

/// The shared scope placement for moving a model to a destination: `(model, destination)`.
pub type DeclarationMoveHost<'a> =
    dyn Fn(&str, &str) -> Result<DeclarationPlacement, RefactorError> + 'a;

/// Original texts keyed by original path, in plan order.
pub type Originals = Vec<(String, String)>;

/// One physical column: `(name, type)`.
pub type PhysicalColumn = (String, String);

/// Replace lines `start..end` with new lines, as contract adoption's YAML source edit plans it.
pub type LineEdit = (usize, usize, Vec<String>);
