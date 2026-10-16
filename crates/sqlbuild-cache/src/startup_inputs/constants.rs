//! Names the startup stamps read.

/// The virtual-environment configuration file of an interpreter prefix.
pub(crate) const VENV_CONFIG: &[u8] = b"pyvenv.cfg";
/// The suffix of the path configuration files `site` processes.
pub(crate) const PATH_FILE_SUFFIX: &[u8] = b".pth";
pub(crate) const SEPARATOR: u8 = b'/';
pub(crate) const CURRENT: &[u8] = b".";
