#[derive(Clone, Debug, PartialEq)]
pub(crate) enum AuthoredValue {
    Null,
    Boolean(bool),
    BareWord(String),
    String(String),
    List(Vec<AuthoredValue>),
    Map(Vec<(String, AuthoredValue)>),
    Set(Vec<AuthoredValue>),
    Tuple(Vec<AuthoredValue>),
    TypedConstant(Vec<(String, AuthoredValue)>),
    InlineSqlHook(String),
    NamedSqlHook(String, Vec<(String, AuthoredValue)>),
    PythonHook(String, Vec<(String, AuthoredValue)>),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct SqlTestFixtureFacts {
    pub(crate) mock: bool,
    pub(crate) empty_fixture_marker: bool,
}
