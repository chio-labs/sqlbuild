//! Host entries: the staying-Python names native code reaches through `sqlbuild._native_host`.

/// What a host entry resolves to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum HostKind {
    Function,
    Class,
    Exception,
    Value,
}

impl HostKind {
    /// The kind as the import test and `_native.HOST_ENTRIES` spell it.
    pub(crate) const fn label(self) -> &'static str {
        match self {
            Self::Function => "function",
            Self::Class => "class",
            Self::Exception => "exception",
            Self::Value => "value",
        }
    }
}

/// Which boundary a host entry crosses; also its group in `HOST_ENTRIES`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum HostEdge {
    Adapter,
    UserCode,
    Executor,
    ThirdParty,
    Facade,
}

impl HostEdge {
    /// The edge as `_native.HOST_ENTRIES` spells it.
    pub(crate) const fn label(self) -> &'static str {
        match self {
            Self::Adapter => "adapter",
            Self::UserCode => "user_code",
            Self::Executor => "executor",
            Self::ThirdParty => "third_party",
            Self::Facade => "facade",
        }
    }
}

/// One host entry: its `sqlbuild._native_host` name, kind and edge.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct HostEntry {
    pub(crate) name: &'static str,
    pub(crate) kind: HostKind,
    pub(crate) edge: HostEdge,
}

/// A host entry by edge and position, from any edge's entry enum.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct HostId {
    pub(crate) edge: HostEdge,
    pub(crate) index: usize,
}
