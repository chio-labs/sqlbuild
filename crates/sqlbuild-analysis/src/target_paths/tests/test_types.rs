use crate::target_paths::models::SqlTestPathFacts;

pub(super) struct SqlTestPathTestCase {
    pub(super) description: &'static str,
    pub(super) facts: SqlTestPathFacts,
    pub(super) expected_path: &'static str,
}

pub(super) struct RunPathTestCase {
    pub(super) description: &'static str,
    pub(super) relative_path: &'static str,
    pub(super) language: &'static str,
    pub(super) expected_model_path: &'static str,
    pub(super) expected_function_path: &'static str,
}

pub(super) struct RuntimeSqlTestCase {
    pub(super) description: &'static str,
    pub(super) statements: Vec<String>,
    pub(super) expected_text: &'static str,
}
