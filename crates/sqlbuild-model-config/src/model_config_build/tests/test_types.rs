use crate::config_values::models::ConfigNode;
use crate::model_config_build::models::ConfigBuildHalt;
use crate::model_config_build::types::ConfigBuildHost;

/// A config node in tests; host handles are plain numbers.
pub(super) type Node = ConfigNode<u8>;

/// An environment of fixed variables; rendering takes `str()` of numbers.
pub(super) struct FixedHost {
    pub(super) environment: Vec<(&'static str, &'static str)>,
}

impl ConfigBuildHost for FixedHost {
    type Handle = u8;
    type Error = String;

    fn environment(&self, name: &str) -> Result<Option<Node>, String> {
        Ok(self
            .environment
            .iter()
            .find(|(key, _)| *key == name)
            .map(|(_, value)| ConfigNode::Str((*value).to_owned())))
    }

    fn render(&self, value: &Node, _label: &str) -> Result<Result<String, String>, String> {
        Ok(match value {
            ConfigNode::Int(number) => Ok(number.to_string()),
            _ => Err("cannot be interpolated".to_owned()),
        })
    }

    fn text_error(&self, _value: &Node) -> String {
        "not text".to_owned()
    }

    fn python_str(&self, _value: &Node, _exact: bool) -> Result<String, String> {
        Err("no host text".to_owned())
    }

    fn typed_hook_entry(&self, _value: &Node) -> Result<bool, String> {
        Ok(false)
    }
}

/// The built values and reads, or why the build stops.
pub(super) type BuildOutcome =
    Result<(Vec<(Node, Node)>, Vec<(&'static str, String)>), ConfigBuildHalt<u8, String>>;

pub(super) struct BuildTestCase {
    pub(super) description: &'static str,
    pub(super) header: Vec<(Node, Node)>,
    pub(super) target_namespace: Option<(Node, Node)>,
    pub(super) expected_outcome: BuildOutcome,
}
