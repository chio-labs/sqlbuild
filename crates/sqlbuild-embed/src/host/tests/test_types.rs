use std::path::{Path, PathBuf};

use crate::host::models::{HostDiscovery, LocatedHost};

/// A console script's first lines and the interpreter it starts; `<dir>` is the script directory.
pub(crate) struct ScriptTestCase {
    pub(crate) description: &'static str,
    pub(crate) head: &'static str,
    pub(crate) expected_interpreter: Option<&'static str>,
}

/// A relocatable script reached through a link, and its interpreter below the temporary root.
pub(crate) struct LinkedScriptTestCase {
    pub(crate) description: &'static str,
    pub(crate) script: &'static str,
    pub(crate) link: &'static str,
    pub(crate) head: &'static str,
    pub(crate) expected_interpreter: &'static str,
}

/// A libpython version report checked against the interpreter's version.
pub(crate) struct VersionTestCase {
    pub(crate) description: &'static str,
    pub(crate) reported: &'static str,
    pub(crate) version: &'static str,
    pub(crate) expected_accepted: bool,
}

/// A `pyvenv.cfg` text and the base home and version read from it.
pub(crate) struct VenvConfigTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected_home: Option<&'static str>,
    pub(crate) expected_version: Option<&'static str>,
}

/// A version text and the release read from it.
pub(crate) struct ReleaseVersionTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected_release: Option<&'static str>,
}

/// Files under an installation prefix and the libpython 3.12 discovery picks; `<arch>` is the CPU.
pub(crate) struct LibraryLayoutTestCase {
    pub(crate) description: &'static str,
    pub(crate) files: &'static [&'static str],
    pub(crate) expected_library: Option<&'static str>,
}

/// An interpreter laid out below a temporary root and what discovery locates for it.
pub(crate) struct LocateTestCase {
    pub(crate) description: &'static str,
    pub(crate) prepare: fn(&Path) -> PathBuf,
    pub(crate) expected_located: fn(&Path) -> LocatedHost,
}

/// What a venv's interpreter answers when asked about itself; `<root>` is the temporary root.
pub(crate) struct ProbeTestCase {
    pub(crate) description: &'static str,
    pub(crate) answer: &'static [&'static str],
    pub(crate) expected_located: fn(&Path) -> LocatedHost,
}

/// A change between two discoveries of a static venv and how often its interpreter was asked.
pub(crate) struct CacheTestCase {
    pub(crate) description: &'static str,
    pub(crate) change: fn(&StaticVenv),
    pub(crate) expected_probes: usize,
    pub(crate) expected_found: fn(&Path) -> HostDiscovery,
}

/// A cached embeddable discovery whose library is then removed.
pub(crate) struct RemovedLibraryTestCase {
    pub(crate) description: &'static str,
    pub(crate) version_line: &'static str,
    pub(crate) library: &'static str,
    pub(crate) expected_first: fn(&Path) -> HostDiscovery,
    pub(crate) expected_after_removal: fn(&Path) -> HostDiscovery,
}

/// A script naming an interpreter that does not exist.
pub(crate) struct MissingInterpreterTestCase {
    pub(crate) description: &'static str,
    pub(crate) head: &'static str,
    pub(crate) expected_found: HostDiscovery,
}

/// A library file that cannot be started and the start of the reason given.
pub(crate) struct StartTestCase {
    pub(crate) description: &'static str,
    pub(crate) library_contents: &'static [u8],
    pub(crate) expected_reason_prefix: &'static str,
}

/// A venv whose static base interpreter counts how often it is asked about itself.
pub(crate) struct StaticVenv {
    pub(crate) root: PathBuf,
    pub(crate) interpreter: PathBuf,
    pub(crate) script: PathBuf,
    pub(crate) cache: PathBuf,
    pub(crate) runs: PathBuf,
}
