//! One model config value.

use crate::types::NodeKind;

/// A config value: the builtin Python types it is made of, or a value only its host understands.
#[derive(Clone, Debug, PartialEq)]
pub enum ConfigNode<H> {
    Null,
    Bool(bool),
    /// An `int` within `i64`.
    Int(i64),
    Float(f64),
    /// A `str` that is valid UTF-8.
    Str(String),
    List(Vec<Self>),
    Tuple(Vec<Self>),
    /// A `dict`'s entries in insertion order.
    Map(Vec<(Self, Self)>),
    /// Any other value, carried by its host handle and read through the facts taken from it.
    Host(Box<HostValue<H>>),
}

/// An opaque value: its host handle, what it reads as, and its items when it is a container.
#[derive(Clone, Debug, PartialEq)]
pub struct HostValue<H> {
    pub handle: H,
    pub facts: HostFacts,
    pub children: HostChildren<H>,
}

/// The cheap facts read of an opaque value when it is converted; anything else is asked of its handle.
#[derive(Clone, Debug, PartialEq)]
pub struct HostFacts {
    pub kind: NodeKind,
    /// The text of a string value, with lone surrogates read as U+FFFD.
    pub text: Option<String>,
    /// Whether `text` is the value's exact text.
    pub strict_text: bool,
    pub integer: Option<i64>,
    pub number: Option<f64>,
}

/// The converted items of an opaque list, tuple or mapping, which config logic walks.
#[derive(Clone, Debug, PartialEq)]
pub enum HostChildren<H> {
    None,
    Items(Vec<ConfigNode<H>>),
    Entries(Vec<(ConfigNode<H>, ConfigNode<H>)>),
}

/// One layer merged over another, and which keys a union replaced rather than overrode.
#[derive(Clone, Debug, PartialEq)]
pub struct LayeredConfig<H> {
    pub entries: Vec<(ConfigNode<H>, ConfigNode<H>)>,
    /// The keys both layers set whose merged value is a union of the two.
    pub unioned_keys: Vec<&'static str>,
}

/// How a cursor bound reads as text: its `str()`, or its `isoformat()` for a date or datetime.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum CursorBound<'a, H> {
    Stringified(&'a ConfigNode<H>),
    Dated(&'a ConfigNode<H>),
}
