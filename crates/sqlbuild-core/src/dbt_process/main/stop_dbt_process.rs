//! Stop an unfinished dbt process: terminate, wait, then kill and wait again.

use std::io;
use std::process::{Child, ExitStatus};
use std::time::Instant;

use crate::dbt_process::constants::{DBT_STOP_POLL, DBT_STOP_WAIT};

/// Terminate a running process with `terminate`, kill it after a second, and reap it.
pub fn stop_dbt_process(mut child: Child, terminate: impl FnOnce(u32)) -> Child {
    if matches!(child.try_wait(), Ok(None)) {
        terminate(child.id());
    }
    if matches!(wait_briefly(&mut child), Ok(Some(_))) {
        return child;
    }
    let _killed: io::Result<()> = child.kill();
    let _reaped: io::Result<Option<ExitStatus>> = wait_briefly(&mut child);
    child
}

fn wait_briefly(child: &mut Child) -> io::Result<Option<ExitStatus>> {
    let deadline: Instant = Instant::now() + DBT_STOP_WAIT;
    loop {
        if let Some(status) = child.try_wait()? {
            return Ok(Some(status));
        }
        if Instant::now() >= deadline {
            return Ok(None);
        }
        std::thread::sleep(DBT_STOP_POLL);
    }
}
