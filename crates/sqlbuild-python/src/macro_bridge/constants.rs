//! Macro call event tags shared with `sqlbuild.compiler.macro_bridge.constants`.

pub(crate) const MACRO_USE: u8 = 0;
pub(crate) const DECLARATION_READ: u8 = 1;
pub(crate) const GENERATED_SQL: u8 = 2;
pub(crate) const ARGUMENT_REFERENCE: u8 = 3;
