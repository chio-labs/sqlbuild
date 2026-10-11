use crate::compiled_project::models::LegacySchemaFile;

/// The error for a model `(name, relative path)` that a legacy schema file still declares.
pub fn legacy_schema_error(
    model: (&str, &str),
    schema_files: &[LegacySchemaFile],
) -> Option<String> {
    crate::compiled_project::_helpers::sources::legacy_schema_error(model, schema_files)
}
