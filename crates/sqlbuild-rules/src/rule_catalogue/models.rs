//! Typed views of catalogue rules, their declared options and the rule text guidance renders.

/// The Python type an option declares for its value or its tuple items.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum OptionKind {
    Bool,
    Int,
    Str,
    Tuple,
    /// Any other Python type, by name; `object` accepts every value.
    Other(String),
}

/// A declared or configured option value with Python's scalar and tuple distinctions.
#[derive(Clone, Debug)]
pub enum OptionValue {
    Bool(bool),
    Int(i64),
    Str(String),
    Tuple(Vec<OptionValue>),
    /// A value of another Python type, by type name.
    Other(String),
}

/// One option a rule declares.
#[derive(Clone, Debug)]
pub struct OptionSpec {
    pub name: String,
    pub description: String,
    pub value_type: OptionKind,
    pub default: OptionValue,
    pub choices: Vec<OptionValue>,
    pub minimum: Option<i64>,
    pub maximum: Option<i64>,
    pub minimum_items: Option<i64>,
    pub item_type: Option<OptionKind>,
}

/// The code and declared options of one catalogue rule.
#[derive(Clone, Debug)]
pub struct CatalogueRule {
    pub code: String,
    pub options: Vec<OptionSpec>,
}

/// One declared option as inspection and guidance show it, with Python `repr` texts.
#[derive(Clone, Debug, Default)]
pub struct OptionText {
    pub name: String,
    pub description: String,
    pub default_repr: String,
    pub effective_repr: String,
}

/// The metadata of one rule that inspection text and guidance render.
#[derive(Clone, Debug, Default)]
pub struct RuleText {
    pub code: String,
    pub family: String,
    pub slug: String,
    pub message: String,
    pub remediation: String,
    pub enabled_by_default: bool,
    pub custom: bool,
    pub source: Option<String>,
    pub options: Vec<OptionText>,
    pub good_example: Option<String>,
}

/// The inputs of one selected rule that the ruleset fingerprint covers.
#[derive(Clone, Debug, Default)]
pub struct FingerprintRule {
    pub code: String,
    pub family: String,
    pub slug: String,
    pub message: String,
    pub remediation: String,
    pub source: Option<String>,
    pub implementation_hash: String,
}

/// One generated skill target and the ownership state of its current content.
#[derive(Clone, Debug)]
pub struct SkillTarget {
    pub path: std::path::PathBuf,
    pub state: String,
}

/// One catalogue rule as `sqb rules list` prints it.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RuleListing {
    pub code: String,
    pub family: String,
    pub message: String,
    pub custom: bool,
    /// The `RuleSubject` value, or `None` when the rule declares none.
    pub subject: Option<String>,
}
