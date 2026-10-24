//! Shapes of query analysis results.

use polyglot_sql::expressions::DataType;

/// One output of a fully annotated query: its name, inferred type, and annotated type.
pub type AnnotatedOutput = (String, Option<String>, Option<DataType>);
