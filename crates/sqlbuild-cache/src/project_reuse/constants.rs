/// Suffix of every stored compile's slot file, which holds its inputs.
pub const REUSE_STORE_SUFFIX: &str = "store";
/// Suffix of the file beside each slot file holding the stored compile's output.
pub const REUSE_OUTPUT_SUFFIX: &str = "output";
/// Suffix of the file beside a recently used slot holding the facts a delta compile patches.
pub const REUSE_IMAGE_SUFFIX: &str = "image";
/// How many of the most recently used slots keep their image.
pub const REUSE_MAX_STORED_IMAGES: usize = 2;
/// Prefix of digests computed natively, so they never equal a Python digest.
pub const NATIVE_DIGEST_PREFIX: &str = "b3:";
/// The sibling of the compiled directory that holds a compile whose Rules failed.
pub const FAILED_COMPILED_DIRECTORY_NAME: &str = "compiled-failed";
