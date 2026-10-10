//! Callback and alias types shared by refactoring planning and its bindings.

use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::DeclarationMoves;

/// Works out which declaration files a model move takes along: `(model, source, destination)`.
pub type DeclarationMoveHost<'a> =
    dyn Fn(&str, &str, &str) -> Result<DeclarationMoves, RefactorError> + 'a;

/// Original texts keyed by original path, in plan order.
pub type Originals = Vec<(String, String)>;
