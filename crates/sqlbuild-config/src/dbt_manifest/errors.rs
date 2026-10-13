//! A dbt manifest SQLBuild cannot read or resolve against.

use crate::dbt_manifest::_helpers::fields::quoted_dbt_ref;
use crate::dbt_manifest::constants::{DBT_REF_FUNCTION, MANIFEST_HELP};

/// `CompileInputError(message, code=code, help=help)`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ManifestError {
    pub code: &'static str,
    pub message: String,
    pub help: Option<String>,
}

impl ManifestError {
    /// No model `name` (in `package_name`, when given) exists in the manifest.
    #[must_use]
    pub fn unknown_model(name: &str, package_name: Option<&str>) -> Self {
        let (target, what) = match package_name {
            Some(package) => (format!("{package}.{name}"), "package/name"),
            None => (name.to_owned(), "name"),
        };
        Self {
            code: "C212",
            message: format!("dbt model '{target}' was not found in manifest"),
            help: Some(format!(
                "Check the {DBT_REF_FUNCTION}(...) {what} or run dbt compile to refresh manifest.json."
            )),
        }
    }

    /// `name` matches models in several packages, listed sorted.
    #[must_use]
    pub fn ambiguous_model(name: &str, mut packages: Vec<String>) -> Self {
        packages.sort();
        Self {
            code: "C213",
            message: format!(
                "dbt model '{name}' is ambiguous across packages: {}",
                packages.join(", ")
            ),
            help: Some(format!(
                "Use {} to choose one dbt model.",
                quoted_dbt_ref(&["package_name", name])
            )),
        }
    }

    /// A model uses `__dbt_ref` but no manifest was found.
    #[must_use]
    pub fn missing_manifest(model_relative_path: &str, ref_name: &str) -> Self {
        Self {
            code: "C214",
            message: format!(
                "Model file {model_relative_path} uses {} but no dbt manifest was found",
                quoted_dbt_ref(&[ref_name])
            ),
            help: Some(MANIFEST_HELP.to_owned()),
        }
    }

    /// dbt and SQLBuild models share these names, sorted.
    #[must_use]
    pub fn shared_model_names(mut names: Vec<String>) -> Option<Self> {
        if names.is_empty() {
            return None;
        }
        names.sort();
        Some(Self {
            code: "C215",
            message: format!("dbt and SQLBuild models share names: {}", names.join(", ")),
            help: Some(
                "Rename either the dbt model or SQLBuild model; owner-qualified names are not supported."
                    .to_owned(),
            ),
        })
    }

    /// The manifest file does not exist.
    #[must_use]
    pub fn missing_manifest_file(path: &str) -> Self {
        Self {
            code: "C210",
            message: format!("dbt manifest file does not exist: {path}"),
            help: Some(MANIFEST_HELP.to_owned()),
        }
    }

    /// The manifest is not the JSON shape SQLBuild reads.
    #[must_use]
    pub fn invalid(detail: &str) -> Self {
        Self {
            code: "C211",
            message: format!("Invalid dbt manifest{detail}"),
            help: None,
        }
    }
}
