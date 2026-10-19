//! Fixed names and limits of interpreter discovery.

/// The Python minor versions SQLBuild supports, and so the only ones `sqb` embeds.
pub const SUPPORTED_MINOR_VERSIONS: [u32; 3] = [12, 13, 14];
/// The leading bytes of the Python CLI script read to find its interpreter.
pub const SCRIPT_HEAD_BYTES: u64 = 4096;
/// The `/bin/sh` line of the shell trampolines pip and uv write for long or relocatable paths.
pub const SHELL_SHEBANG: &str = "#!/bin/sh";
/// The start of a trampoline's second line, before the interpreter.
pub const TRAMPOLINE_PREFIX: &str = "'''exec' ";
/// The end of a trampoline's second line, after the interpreter.
pub const TRAMPOLINE_SUFFIX: &str = " \"$0\" \"$@\"";
/// uv's relocatable interpreter: the named file in the script's resolved directory.
pub const RELOCATABLE_DIRECTORY: &str = "\"$(dirname -- \"$(realpath -- \"$0\")\")\"/";
/// The virtual environment configuration file beside or above a venv interpreter.
pub const VENV_CONFIG: &str = "pyvenv.cfg";
/// Library directories below an installation prefix, tried in order.
pub const LIBRARY_DIRECTORIES: [&str; 2] = ["lib", "lib64"];
/// The domain line at the top of every interpreter cache file; bump when its contents change.
pub const CACHE_FORMAT: &str = "sqlbuild-interpreter-cache-1";
/// The cache directory below the user cache directory.
pub const CACHE_DIRECTORY: [&str; 2] = ["sqlbuild", "interpreters"];
/// The cache entry kind of an interpreter `sqb` can embed.
pub const CACHED_EMBEDDABLE: &str = "embed";
/// The cache entry kind of an interpreter `sqb` runs by `exec`.
pub const CACHED_EXEC: &str = "exec";
/// Prints, one per line: shared build flag, library directory and name, base prefix, version.
pub const PROBE_SCRIPT: &str = "import sys, sysconfig\n\
v = sysconfig.get_config_var\n\
print(v('Py_ENABLE_SHARED') or 0, v('LIBDIR') or '', v('INSTSONAME') or '', \
sys.base_prefix, '%d.%d' % sys.version_info[:2], sep='\\n')\n";
/// The `Py_ENABLE_SHARED` value of an interpreter built with a shared libpython.
pub const SHARED_BUILD: &str = "1";
/// A release version has at least a major and a minor number.
pub const MINIMUM_VERSION_PARTS: usize = 2;
/// The marker CPython puts in the version of a free-threaded build, which the extension cannot load in.
pub const FREE_THREADING_MARKER: &str = "free-threading";
