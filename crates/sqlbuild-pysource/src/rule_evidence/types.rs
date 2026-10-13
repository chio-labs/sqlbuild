//! The import bindings of one test module.

use std::collections::HashMap;

/// Each top-level imported name and its `(module, symbol)`; `import x` has no symbol.
pub(crate) type Imports = HashMap<String, (String, Option<String>)>;
