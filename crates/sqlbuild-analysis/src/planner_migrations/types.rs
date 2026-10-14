//! Query proof boundary for candidate selection.

/// Prove the entire query change using the proposed column rename pairs.
pub type RenameProof<'a, E> = dyn FnMut(&[(String, String)]) -> Result<bool, E> + 'a;
