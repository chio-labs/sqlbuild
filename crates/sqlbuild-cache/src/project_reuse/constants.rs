/// Suffix of every stored compile's slot file, which holds its inputs.
pub const REUSE_STORE_SUFFIX: &str = "store";
/// Suffix of the file beside each slot file holding the stored compile's output.
pub const REUSE_OUTPUT_SUFFIX: &str = "output";
/// Prefix of digests computed natively, so they never equal a Python digest.
pub const NATIVE_DIGEST_PREFIX: &str = "b3:";
