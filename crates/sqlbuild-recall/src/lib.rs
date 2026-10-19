//! Recall: the records of every invocation, their SQLite and ClickHouse schema and views, retention, the `[recall]` settings, the local SQLite store and its delivery thread.

#![forbid(unsafe_code)]

pub mod clickhouse;
pub mod records;
pub mod schema;
pub mod settings;
pub mod store;
pub mod writer;
