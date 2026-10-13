//! Load selection errors.

/// A `--select` or `--exclude` name that matches no managed source or loader.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UnknownLoadSelector {
    pub name: String,
}
