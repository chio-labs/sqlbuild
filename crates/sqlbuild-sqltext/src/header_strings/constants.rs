//! Header string delimiters, the prose keys that fold, and the quote errors and their help.

/// The delimiter of a triple-quoted header string.
pub const TRIPLE_QUOTE: &str = "\"\"\"";
/// Characters in a triple-quote delimiter.
pub const TRIPLE_QUOTE_LENGTH: usize = 3;
/// The most double quotes that may end a triple-quoted string: two of them belong to the text.
pub const LONGEST_CLOSING_RUN: usize = 5;
/// The header key whose string values are folded prose.
pub const DESCRIPTION_KEY: &str = "description";
/// The header key whose free-form values are never prose, even under a `description` key.
pub const META_KEY: &str = "meta";
/// The header key whose list items are audits, whose `description` option is prose.
pub const AUDITS_KEY: &str = "audits";
/// What a prose value stores for a blank line: a paragraph break.
pub const PARAGRAPH_BREAK: &str = "\n\n";

/// Header syntax errors end with ` at position <character offset in the header>`.
pub const POSITION_SUFFIX: &str = " at position ";
pub const DOUBLE_QUOTE_INSIDE: &str = "double quote inside a \"...\" string";
pub const SINGLE_QUOTE_INSIDE: &str = "single quote inside a '...' string";
pub const TRIPLE_QUOTE_INSIDE: &str = "\"\"\" inside a \"\"\"...\"\"\" string";
pub const UNCLOSED_TRIPLE_QUOTE: &str = "unclosed \"\"\" string starting";

pub const DOUBLE_QUOTE_INSIDE_MESSAGE: &str = "a double quote ends this \"...\" string early; use \"\"\"…\"\"\" for text containing double quotes";
pub const DOUBLE_QUOTE_INSIDE_HELP: &str = "write the text between triple quotes, where quotes need no escaping: description \"\"\"Matches \"Miss\".\"\"\"; sqb format --fix rewrites a description that escapes its quotes as \\\" or doubles them as \"\"";
pub const SINGLE_QUOTE_INSIDE_MESSAGE: &str =
    "a single quote ends this '...' string early; use \"...\" for text containing single quotes";
pub const SINGLE_QUOTE_INSIDE_HELP: &str = "write the text between double quotes, description \"Matches 'Miss'.\", or double the quote: 'it''s'";
pub const TRIPLE_QUOTE_INSIDE_MESSAGE: &str =
    "\"\"\" inside a \"\"\"...\"\"\" string ends it early";
pub const TRIPLE_QUOTE_INSIDE_HELP: &str = "a \"\"\"...\"\"\" string ends at the next \"\"\"; reword the text so it has no three double quotes in a row";
pub const UNCLOSED_TRIPLE_QUOTE_MESSAGE: &str = "this \"\"\" string is never closed";
pub const UNCLOSED_TRIPLE_QUOTE_HELP: &str = "end the text with \"\"\"";

/// Code points from here on are not ASCII; text running on into one continues a word.
pub(crate) const FIRST_NON_ASCII: u32 = 0x80;
