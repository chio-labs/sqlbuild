//! Stored bytes of one recorded macro call.

use sqlbuild_cache::store::errors::StoreDecodeError;
use sqlbuild_cache::store::models::{RecordReader, RecordWriter};

use crate::macro_calls::models::{MacroCallEntry, MacroCallEvent};

const MACRO_USE: u64 = 0;
const DECLARATION_READ: u64 = 1;
const GENERATED_SQL: u64 = 2;
const ARGUMENT_REFERENCE: u64 = 3;

pub(crate) fn encode_entry(entry: &MacroCallEntry) -> Vec<u8> {
    let mut writer: RecordWriter = RecordWriter::default();
    writer.put_str(&entry.sql);
    writer.put_u64(entry.relations.len() as u64);
    for (kind, name) in &entry.relations {
        writer.put_str(kind);
        writer.put_str(name);
    }
    writer.put_u64(entry.events.len() as u64);
    for event in &entry.events {
        let (tag, first, second) = match event {
            MacroCallEvent::MacroUse { name } => (MACRO_USE, name.as_str(), ""),
            MacroCallEvent::DeclarationRead { kind, name } => {
                (DECLARATION_READ, kind.as_str(), name.as_str())
            }
            MacroCallEvent::GeneratedSql { macro_name, sql } => {
                (GENERATED_SQL, macro_name.as_str(), sql.as_str())
            }
            MacroCallEvent::ArgumentReference { kind, name } => {
                (ARGUMENT_REFERENCE, kind.as_str(), name.as_str())
            }
        };
        writer.put_u64(tag);
        writer.put_str(first);
        writer.put_str(second);
    }
    writer.into_bytes()
}

/// The entry stored by [`encode_entry`]; bytes this build did not write are a decode error.
pub(crate) fn decode_entry(bytes: &[u8]) -> Result<MacroCallEntry, StoreDecodeError> {
    let mut reader: RecordReader<'_> = RecordReader::new(bytes);
    let sql: String = reader.string()?;
    let relation_count: u64 = reader.u64()?;
    let mut relations: Vec<(String, String)> = Vec::new();
    for _ in 0..relation_count {
        relations.push((reader.string()?, reader.string()?));
    }
    let event_count: u64 = reader.u64()?;
    let mut events: Vec<MacroCallEvent> = Vec::new();
    for _ in 0..event_count {
        let tag: u64 = reader.u64()?;
        let first: String = reader.string()?;
        let second: String = reader.string()?;
        events.push(match tag {
            MACRO_USE if second.is_empty() => MacroCallEvent::MacroUse { name: first },
            DECLARATION_READ => MacroCallEvent::DeclarationRead {
                kind: first,
                name: second,
            },
            GENERATED_SQL => MacroCallEvent::GeneratedSql {
                macro_name: first,
                sql: second,
            },
            ARGUMENT_REFERENCE => MacroCallEvent::ArgumentReference {
                kind: first,
                name: second,
            },
            _ => return Err(StoreDecodeError),
        });
    }
    reader.finish()?;
    Ok(MacroCallEntry {
        sql,
        relations,
        events,
    })
}
