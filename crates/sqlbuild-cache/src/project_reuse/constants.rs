/// The native store kind holding one stored compile per selected target.
pub const REUSE_STORE_KIND: &str = "project-reuse";
/// The store environment; bumped when the stored records change shape.
pub const REUSE_STORE_ENVIRONMENT: &str = "project-reuse-records-1";
/// Suffix of every reuse store file.
pub const REUSE_STORE_SUFFIX: &str = "store";
/// Prefix of digests computed natively, so they never equal a Python digest.
pub const NATIVE_DIGEST_PREFIX: &str = "b3:";
