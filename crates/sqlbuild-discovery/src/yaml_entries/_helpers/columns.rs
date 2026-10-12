//! The `columns` list of a seed or source entry.

use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::header_metadata::main::parse_audit_list::parse_audit_list;
use sqlbuild_model_config::types::{AuthoredNode, NodeKind};

use crate::yaml_entries::_helpers::fields::{
    Site, get, optional_bool, optional_mapping, optional_text, reject_unknown_keys, required_text,
};
use crate::yaml_entries::models::ParsedYamlColumn;

const NOT_NULL_AUDIT: &str = "not_null";

/// `_parse_columns` of a seed or source entry.
pub(crate) fn yaml_columns<N: AuthoredNode>(
    entries: &[(N, N)],
    site: Site<'_>,
    allowed: Option<&[&str]>,
) -> Result<Vec<ParsedYamlColumn<N>>, ConfigError> {
    let Some(raw) = get(entries, "columns") else {
        return Ok(Vec::new());
    };
    if raw.kind() != NodeKind::List {
        return Err(site.error("columns must be a list"));
    }
    let label: String = format!("{} column", site.label);
    let column_site: Site<'_> = Site {
        path: site.path,
        label: &label,
    };
    let mut columns: Vec<ParsedYamlColumn<N>> = Vec::new();
    for raw_column in raw.items() {
        if raw_column.kind() != NodeKind::Map {
            return Err(site.error("columns must contain only mappings"));
        }
        let column: Vec<(N, N)> = raw_column.entries();
        if let Some(allowed) = allowed {
            reject_unknown_keys(&column, allowed, column_site)?;
        }
        let name: N = required_text(&column, "name", column_site)?;
        let nullable: Option<N> = optional_bool(&column, "nullable", column_site)?;
        let audits = parse_audit_list(get(&column, "audits"), site.path, &label, false)?;
        let declares_nullable: bool = nullable
            .as_ref()
            .is_some_and(|value| value.kind() == NodeKind::Bool(true));
        if declares_nullable
            && audits
                .iter()
                .any(|audit| audit.definition_name.is_text(NOT_NULL_AUDIT))
        {
            return Err(ConfigError::compile(format!(
                "{} column '{}' cannot set nullable = true and audit not_null",
                site.path,
                name.python_str()
            )));
        }
        columns.push(ParsedYamlColumn {
            name,
            column_type: optional_text(&column, "type", column_site)?,
            nullable,
            description: optional_text(&column, "description", column_site)?,
            meta: optional_mapping(&column, "meta", column_site)?,
            audits,
        });
    }
    Ok(columns)
}
