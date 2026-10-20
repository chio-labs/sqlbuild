//! Positional rows shared by the compiled views and the input loops that fill them.

positional_record! {
    extract, into;
    /// `(kind, name, package, call argument count)`.
    #[derive(Clone, Debug, PartialEq, Eq)]
    pub(crate) struct ReferenceRow {
        pub(crate) kind: String,
        pub(crate) name: String,
        pub(crate) package: Option<String>,
        pub(crate) call_argument_count: Option<usize>,
    }
}
