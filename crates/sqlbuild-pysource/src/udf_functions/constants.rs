//! The decorator and imports that mark a warehouse Python function file.

/// The decorator name a UDF function is marked with, bare or as an attribute.
pub const UDF_DECORATOR_NAME: &str = "udf";
/// The modules whose `udf` import the warehouse body drops.
pub const UDF_IMPORT_MODULES: [&str; 2] = ["sqlbuild", "sqlbuild.functions"];
/// The keywords `@udf(...)` accepts.
pub const UDF_KEYS: [&str; 9] = [
    "description",
    "arguments",
    "returns",
    "runtime_version",
    "entry_point",
    "packages",
    "database",
    "schema",
    "tags",
];
