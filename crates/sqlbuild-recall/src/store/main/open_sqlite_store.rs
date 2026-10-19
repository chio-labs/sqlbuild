//! `open_sqlite_store`: open, or create, a SQLite Recall store with its pragmas.

use std::path::Path;
use std::time::Duration;

use rusqlite::config::DbConfig;
use rusqlite::{Connection, OpenFlags};

use crate::schema::constants::MINIMUM_SQLITE_VERSION;
use crate::store::_helpers::sqlite::{checked, store_error};
use crate::store::constants::{BUSY_TIMEOUT_MS, JOURNAL_SIZE_LIMIT_BYTES};
use crate::store::errors::{StoreError, StoreErrorKind};
use crate::store::models::{OpenMode, SqliteStore};

fn check_version() -> Result<(), StoreError> {
    let version: i32 = rusqlite::version_number();
    let (major, minor) = MINIMUM_SQLITE_VERSION;
    let minimum = i32::try_from(major * 1_000_000 + minor * 1_000).unwrap_or(i32::MAX);
    if version < minimum {
        return Err(StoreError::new(
            StoreErrorKind::Version,
            format!(
                "Recall needs SQLite {major}.{minor} or newer; this build has {}",
                rusqlite::version()
            ),
        ));
    }
    Ok(())
}

fn create_parent(path: &Path) -> Result<(), StoreError> {
    let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    else {
        return Ok(());
    };
    std::fs::create_dir_all(parent).map_err(|error| {
        let kind = if error.kind() == std::io::ErrorKind::PermissionDenied
            || error.kind() == std::io::ErrorKind::ReadOnlyFilesystem
        {
            StoreErrorKind::Permission
        } else {
            StoreErrorKind::Other
        };
        StoreError::new(
            kind,
            format!("cannot create directory {}: {error}", parent.display()),
        )
    })
}

/// The open store at `path`. Writers create the file and its directory and switch it to WAL; a new file gets incremental auto-vacuum before any table exists.
pub fn open_sqlite_store(path: &Path, mode: OpenMode) -> Result<SqliteStore, StoreError> {
    check_version()?;
    let connection: Connection = match mode {
        OpenMode::ReadWrite => {
            create_parent(path)?;
            checked(
                Connection::open_with_flags(
                    path,
                    OpenFlags::SQLITE_OPEN_READ_WRITE
                        | OpenFlags::SQLITE_OPEN_CREATE
                        | OpenFlags::SQLITE_OPEN_NO_MUTEX,
                ),
                &format!("cannot open {}", path.display()),
            )?
        }
        OpenMode::ReadOnly => {
            if !path.exists() {
                return Err(StoreError::new(
                    StoreErrorKind::NotFound,
                    format!("no Recall store at {}", path.display()),
                ));
            }
            checked(
                Connection::open_with_flags(
                    path,
                    OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
                ),
                &format!("cannot open {}", path.display()),
            )?
        }
    };
    checked(
        connection.busy_timeout(Duration::from_millis(BUSY_TIMEOUT_MS)),
        "set busy timeout",
    )?;
    if mode == OpenMode::ReadWrite {
        let page_count: i64 = checked(
            connection.query_row("PRAGMA page_count", [], |row| row.get(0)),
            &format!("cannot read {}", path.display()),
        )?;
        if page_count == 0 {
            checked(
                connection.execute_batch("PRAGMA auto_vacuum = INCREMENTAL"),
                "enable incremental vacuum",
            )?;
        }
        let journal: String = connection
            .query_row("PRAGMA journal_mode = WAL", [], |row| row.get(0))
            .map_err(|error| store_error(&error, &format!("cannot write {}", path.display())))?;
        if !journal.eq_ignore_ascii_case("wal") {
            return Err(StoreError::new(
                StoreErrorKind::Permission,
                format!("cannot switch {} to WAL mode", path.display()),
            ));
        }
        checked(
            connection.execute_batch(&format!(
                "PRAGMA synchronous = NORMAL; PRAGMA journal_size_limit = {JOURNAL_SIZE_LIMIT_BYTES}; \
                 PRAGMA wal_autocheckpoint = 0;"
            )),
            "set store pragmas",
        )?;
        checked(
            connection.set_db_config(DbConfig::SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, true),
            "keep the WAL at close",
        )?;
    } else {
        checked(
            connection.execute_batch("PRAGMA query_only = ON"),
            "open store read-only",
        )?;
    }
    Ok(SqliteStore {
        connection,
        path: path.to_path_buf(),
    })
}
