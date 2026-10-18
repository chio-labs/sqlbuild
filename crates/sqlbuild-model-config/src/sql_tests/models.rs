//! A validated SQL `TEST(...)` block.

use sqlbuild_core::models::SqlValue;

/// One declared parameter: name, `SqlValueKind` value and nullability.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqlTestParameter {
    pub name: String,
    pub value_type: &'static str,
    pub nullable: bool,
}

/// One named case and its typed parameter values, in declaration order.
#[derive(Clone, Debug, PartialEq)]
pub struct SqlTestCase {
    pub name: String,
    pub values: Vec<(String, SqlValue)>,
}

/// The fields `build_sql_test_block` derives from one TEST block's header and body.
#[derive(Clone, Debug, PartialEq)]
pub struct SqlTestBlock {
    pub name: Option<String>,
    pub mode: &'static str,
    pub parameters: Vec<SqlTestParameter>,
    pub cases: Vec<SqlTestCase>,
    pub cursor_start: Option<String>,
    pub cursor_end: Option<String>,
    pub timeout: Option<String>,
}
