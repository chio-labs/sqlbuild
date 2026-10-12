//! The context methods and parameters that carry SQL text.

/// Context methods whose first argument is SQL.
pub(crate) const SQL_METHOD_NAMES: [&str; 2] = ["query", "execute_sql"];

/// The keyword name of the SQL argument.
pub(crate) const SQL_PARAMETER_NAME: &str = "sql";

/// Parameter names preferred as the context over the first parameter.
pub(crate) const CONTEXT_PARAMETER_NAMES: [&str; 4] = ["ctx", "context", "_ctx", "hook_context"];
