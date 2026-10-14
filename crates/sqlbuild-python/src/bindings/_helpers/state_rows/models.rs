//! The layout of one append-only migration state table as the bindings use it.

/// Which migration state table a request reads or writes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum EventTable {
    Model,
    Column,
    OldName,
}

/// Name, columns, event relation attribute and messages of one migration state table.
#[derive(Clone, Copy, Debug)]
pub(crate) struct EventTableLayout {
    pub table: EventTable,
    pub name: &'static str,
    pub columns: &'static [&'static str],
    pub relation_attribute: &'static str,
    pub state_message: &'static str,
    pub event_message: &'static str,
}
