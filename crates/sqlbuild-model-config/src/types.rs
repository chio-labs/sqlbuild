//! The shape of one authored header value as the parser inspects it.

/// One authored value's kind; containers and strings are read through [`AuthoredNode`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NodeKind {
    Null,
    Bool(bool),
    /// An integer that is not a boolean, with its sign.
    Int {
        negative: bool,
    },
    Str,
    List,
    Tuple,
    Map,
    /// Any other value: tuples, floats, markers and objects.
    Other,
}

/// Read access to an authored value tree owned by the caller, such as Python objects.
pub trait AuthoredNode: Clone {
    /// Return this value's kind.
    fn kind(&self) -> NodeKind;
    /// Return an integer that is not a boolean and fits in `i64`, or `None`.
    fn integer(&self) -> Option<i64>;
    /// Python's `float(value)` of a non-boolean integer (infinite beyond the range), or `None`.
    fn number(&self) -> Option<f64>;
    /// Return the text of a string value, or `None` for another value.
    fn text(&self) -> Option<String>;
    /// Return whether this is a string value equal to `text`.
    fn is_text(&self, text: &str) -> bool;
    /// Apply `read` to a string value's text, or return `None` for another value.
    fn with_text<R>(&self, read: impl FnOnce(&str) -> R) -> Option<R>;
    /// Return Python's `str(value)`.
    fn python_str(&self) -> String;
    /// Return Python's `repr(value)`.
    fn python_repr(&self) -> String;
    /// Return whether the value is a `datetime.date` or `datetime.datetime`.
    fn is_date_like(&self) -> bool;
    /// Return a list's or tuple's items in order.
    fn items(&self) -> Vec<Self>;
    /// Return a mapping's entries in insertion order.
    fn entries(&self) -> Vec<(Self, Self)>;
}
