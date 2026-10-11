//! Validated enum and constant declarations.

use sqlbuild_core::models::SqlValue;

/// An enum member value: text, or an integer in its decimal digits.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum EnumValue {
    Text(String),
    Integer(String),
}

/// `EnumDeclaration` without its path and owner.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EnumFacts {
    pub name: String,
    pub members: Vec<(String, EnumValue)>,
    pub scalar_type: &'static str,
}

/// `ConstantDeclaration` without its path and owner.
#[derive(Clone, Debug, PartialEq)]
pub struct ConstantFacts {
    pub name: String,
    pub value: SqlValue,
    pub render_as: Option<&'static str>,
}

/// Where declarations are authored: the path diagnostics name and the owning model, if any.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DeclarationSite<'a> {
    pub file_path: &'a str,
    pub model_name: Option<&'a str>,
}
