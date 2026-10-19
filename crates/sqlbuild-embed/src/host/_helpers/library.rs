//! The crate's only unsafe code: `dlopen`, `dlsym`, two CPython calls and the start-up environment.

#![allow(unsafe_code)]

#[cfg(unix)]
use std::ffi::CStr;
use std::ffi::CString;
use std::path::Path;

/// `const char *Py_GetVersion(void)`, unchanged in every CPython 3 release.
#[cfg(unix)]
type VersionFunction = unsafe extern "C" fn() -> *const libc::c_char;
/// `int Py_BytesMain(int argc, char **argv)`, unchanged since CPython 3.8.
#[cfg(unix)]
type MainFunction = unsafe extern "C" fn(libc::c_int, *mut *mut libc::c_char) -> libc::c_int;

/// A libpython loaded for the rest of the process; it is never unloaded.
pub(crate) struct LoadedPython {
    #[cfg(unix)]
    handle: *mut libc::c_void,
}

/// The loader's last error message, which `dlerror` owns until the next loader call.
#[cfg(unix)]
fn last_error() -> String {
    let message: *const libc::c_char = unsafe { libc::dlerror() };
    if message.is_null() {
        return "unknown loader error".to_owned();
    }
    unsafe { CStr::from_ptr(message) }
        .to_string_lossy()
        .into_owned()
}

#[cfg(unix)]
fn path_text(path: &Path) -> Result<CString, String> {
    use std::os::unix::ffi::OsStrExt;
    CString::new(path.as_os_str().as_bytes())
        .map_err(|_| format!("{} contains a NUL byte", path.display()))
}

impl LoadedPython {
    /// Load `library` with every symbol bound now and global, so the extensions it imports link.
    #[cfg(unix)]
    pub(crate) fn load(library: &Path) -> Result<Self, String> {
        let name: CString = path_text(library)?;
        let flags: libc::c_int = libc::RTLD_NOW | libc::RTLD_GLOBAL;
        let handle: *mut libc::c_void = unsafe { libc::dlopen(name.as_ptr(), flags) };
        if handle.is_null() {
            return Err(format!(
                "cannot load {}: {}",
                library.display(),
                last_error()
            ));
        }
        Ok(Self { handle })
    }

    #[cfg(not(unix))]
    pub(crate) fn load(library: &Path) -> Result<Self, String> {
        Err(format!(
            "cannot load {}: not supported on this platform",
            library.display()
        ))
    }

    /// The address of `name` in the loaded library.
    #[cfg(unix)]
    fn symbol(&self, name: &CStr) -> Result<*mut libc::c_void, String> {
        let address: *mut libc::c_void = unsafe { libc::dlsym(self.handle, name.as_ptr()) };
        if address.is_null() {
            return Err(format!(
                "libpython has no {}: {}",
                name.to_string_lossy(),
                last_error()
            ));
        }
        Ok(address)
    }

    /// The static text `Py_GetVersion()` returns, which CPython allows before initialisation.
    #[cfg(unix)]
    pub(crate) fn version(&self) -> Result<String, String> {
        let address: *mut libc::c_void = self.symbol(c"Py_GetVersion")?;
        let function: VersionFunction = unsafe { std::mem::transmute(address) };
        let text: *const libc::c_char = unsafe { function() };
        if text.is_null() {
            return Err("libpython reports no version".to_owned());
        }
        Ok(unsafe { CStr::from_ptr(text) }
            .to_string_lossy()
            .into_owned())
    }

    #[cfg(not(unix))]
    pub(crate) fn version(&self) -> Result<String, String> {
        Err("not supported on this platform".to_owned())
    }

    /// Set `environment` while no other thread exists, then return `Py_BytesMain(arguments)`.
    #[cfg(unix)]
    pub(crate) fn run_main(
        &self,
        arguments: &[CString],
        environment: &[(&str, &str)],
    ) -> Result<i32, String> {
        let address: *mut libc::c_void = self.symbol(c"Py_BytesMain")?;
        let function: MainFunction = unsafe { std::mem::transmute(address) };
        let count = libc::c_int::try_from(arguments.len())
            .map_err(|_| "too many arguments for Python".to_owned())?;
        let mut pointers: Vec<*mut libc::c_char> = arguments
            .iter()
            .map(|argument| argument.as_ptr().cast_mut())
            .chain(std::iter::once(std::ptr::null_mut()))
            .collect();
        for (name, value) in environment {
            unsafe { std::env::set_var(name, value) };
        }
        Ok(unsafe { function(count, pointers.as_mut_ptr()) })
    }

    #[cfg(not(unix))]
    pub(crate) fn run_main(
        &self,
        _arguments: &[CString],
        _environment: &[(&str, &str)],
    ) -> Result<i32, String> {
        Err("not supported on this platform".to_owned())
    }
}
