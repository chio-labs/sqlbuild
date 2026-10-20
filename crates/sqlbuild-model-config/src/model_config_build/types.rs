//! What the model config build asks of its caller.

use crate::config_values::models::ConfigNode;
use crate::config_values::types::HostObject;
use crate::model_config_build::models::ConfigBuildHalt;

/// The process environment, project-var rendering and exact text errors, owned by the caller.
pub trait ConfigBuildHost {
    /// The caller's handle of an opaque value.
    type Handle: HostObject;
    /// An error the caller raises, held until the build stops.
    type Error;

    /// The environment variable `name`, or `None` when it is not set.
    fn environment(&self, name: &str) -> Result<Option<ConfigNode<Self::Handle>>, Self::Error>;
    /// A non-string value as interpolated text, or the message of a value that cannot be.
    fn render(
        &self,
        value: &ConfigNode<Self::Handle>,
        label: &str,
    ) -> Result<Result<String, String>, Self::Error>;
    /// The error reading `value` as exact text raises.
    fn text_error(&self, value: &ConfigNode<Self::Handle>) -> Self::Error;
    /// Python's `str(value)` of a value that is not a plain scalar; `exact` rejects lone surrogates.
    fn python_str(
        &self,
        value: &ConfigNode<Self::Handle>,
        exact: bool,
    ) -> Result<String, Self::Error>;
    /// Whether `value` is a typed hook entry.
    fn typed_hook_entry(&self, value: &ConfigNode<Self::Handle>) -> Result<bool, Self::Error>;
}

/// A config value of the build host `B`.
pub type HostNode<B> = ConfigNode<<B as ConfigBuildHost>::Handle>;
/// Config entries of the build host `B`.
pub type HostEntries<B> = Vec<(HostNode<B>, HostNode<B>)>;
/// Why a build over the host `B` stops.
pub type HostHalt<B> =
    ConfigBuildHalt<<B as ConfigBuildHost>::Handle, <B as ConfigBuildHost>::Error>;
