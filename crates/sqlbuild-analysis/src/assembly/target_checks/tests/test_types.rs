use crate::assembly::target_checks::errors::TargetError;

pub(crate) struct MessageTestCase {
    pub(crate) description: &'static str,
    pub(crate) error: TargetError,
    pub(crate) expected_message: &'static str,
}

pub(crate) struct SchemaTestCase {
    pub(crate) description: &'static str,
    pub(crate) schema: Option<&'static str>,
    pub(crate) expected_schema: Option<&'static str>,
}

pub(crate) struct NamespaceTestCase {
    pub(crate) description: &'static str,
    pub(crate) namespaces: &'static [(Option<&'static str>, Option<&'static str>)],
    pub(crate) expected_namespace: Option<(Option<&'static str>, Option<&'static str>)>,
}
