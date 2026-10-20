//! `${...}` templates in config values expanded over the build's variables, environment and context.

use std::cell::RefCell;

use crate::config_values::main::config_entry::config_entry;
use crate::config_values::main::plain_scalar_text::plain_scalar_text;
use crate::config_values::models::{ConfigNode, HostChildren};
use crate::config_values::types::ConfigEntries;
use crate::errors::ConfigError;
use crate::model_config_build::constants::{CONTEXT_READ, ENVIRONMENT_READ, TEMPLATE_OPEN_TOKEN};
use crate::model_config_build::models::ConfigBuildHalt;
use crate::model_config_build::types::{ConfigBuildHost, HostEntries, HostHalt, HostNode};
use crate::templates::main::expand_template_string::expand_template_string;
use crate::templates::main::template_error_message::template_error_message;
use crate::templates::models::{
    ContextValue, Scalar, StringExpansion, TemplateFailure, TemplateOptions,
};
use crate::templates::types::TemplateHost;
use crate::types::{AuthoredNode, NodeKind};

/// What one expansion reads: variables, the caller's environment and context values.
pub(crate) struct ExpansionSources<'a, B: ConfigBuildHost> {
    pub(crate) host: &'a B,
    pub(crate) variables: &'a [(HostNode<B>, HostNode<B>)],
    pub(crate) context: ConfigEntries<B::Handle>,
}

/// One expansion's template host, holding the first caller error and recording reads.
struct BuildTemplateHost<'a, B: ConfigBuildHost> {
    sources: ExpansionSources<'a, B>,
    label: &'a str,
    reads: RefCell<Vec<(&'static str, String)>>,
    raised: RefCell<Option<B::Error>>,
}

impl<B: ConfigBuildHost> BuildTemplateHost<'_, B> {
    fn hold(&self, error: B::Error) -> TemplateFailure {
        let _ = self.raised.borrow_mut().get_or_insert(error);
        TemplateFailure::Host
    }

    /// The exact text of a string value, else the caller's error.
    fn exact_text<'v>(&self, value: &'v ConfigNode<B::Handle>) -> Result<&'v str, TemplateFailure> {
        match value {
            ConfigNode::Str(text) => Ok(text),
            ConfigNode::Host(host) if host.facts.strict_text => {
                host.facts.text.as_deref().ok_or(TemplateFailure::Host)
            }
            _ => Err(self.hold(self.sources.host.text_error(value))),
        }
    }

    fn halt(&self, failure: TemplateFailure) -> HostHalt<B> {
        match failure {
            TemplateFailure::Missing(error) | TemplateFailure::Invalid(error) => {
                ConfigBuildHalt::Config(ConfigError::compile(template_error_message(
                    &error, self.label,
                )))
            }
            TemplateFailure::Host => match self.raised.borrow_mut().take() {
                Some(error) => ConfigBuildHalt::Host(error),
                None => ConfigBuildHalt::Config(ConfigError::compile(
                    "template expansion stopped without an error".to_owned(),
                )),
            },
        }
    }
}

impl<B: ConfigBuildHost> TemplateHost for BuildTemplateHost<'_, B> {
    type Value = ConfigNode<B::Handle>;

    fn variable(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure> {
        Ok(config_entry(self.sources.variables, name).cloned())
    }

    fn environment(&self, name: &str) -> Result<Option<Self::Value>, TemplateFailure> {
        self.reads
            .borrow_mut()
            .push((ENVIRONMENT_READ, name.to_owned()));
        self.sources
            .host
            .environment(name)
            .map_err(|error| self.hold(error))
    }

    fn context(&self, name: &str) -> Result<ContextValue<Self::Value>, TemplateFailure> {
        self.reads
            .borrow_mut()
            .push((CONTEXT_READ, name.to_owned()));
        Ok(match config_entry(&self.sources.context, name) {
            None => ContextValue::Unknown,
            Some(ConfigNode::Null) => ContextValue::Unavailable,
            Some(value) => ContextValue::Value(value.clone()),
        })
    }

    fn text(&self, text: &str) -> Result<Self::Value, TemplateFailure> {
        Ok(ConfigNode::Str(text.to_owned()))
    }

    fn boolean(&self, flag: bool) -> Result<Self::Value, TemplateFailure> {
        Ok(ConfigNode::Bool(flag))
    }

    fn null(&self) -> Self::Value {
        ConfigNode::Null
    }

    fn scalar(&self, value: &Self::Value) -> Result<Scalar, TemplateFailure> {
        match value {
            ConfigNode::Null => Ok(Scalar::Null),
            ConfigNode::Bool(flag) => Ok(Scalar::Bool(*flag)),
            _ => match plain_scalar_text(value, false) {
                Some(text) => Ok(Scalar::Text(text)),
                None => self
                    .sources
                    .host
                    .python_str(value, true)
                    .map(Scalar::Text)
                    .map_err(|error| self.hold(error)),
            },
        }
    }

    fn render(&self, value: &Self::Value, label: &str) -> Result<String, TemplateFailure> {
        if let ConfigNode::Str(text) = value {
            return Ok(text.clone());
        }
        match self.sources.host.render(value, label) {
            Ok(Ok(text)) => Ok(text),
            Ok(Err(message)) => Err(TemplateFailure::Invalid(
                crate::templates::errors::TemplateError::Message(message),
            )),
            Err(error) => Err(self.hold(error)),
        }
    }

    fn label(&self) -> &str {
        self.label
    }
}

/// Each item expanded.
fn expanded_items<B: ConfigBuildHost>(
    host: &BuildTemplateHost<'_, B>,
    values: &[HostNode<B>],
    options: TemplateOptions,
) -> Result<Vec<HostNode<B>>, TemplateFailure> {
    values
        .iter()
        .map(|item| expanded(host, item, options))
        .collect()
}

/// Each entry's value expanded under its key.
fn expanded_entries<B: ConfigBuildHost>(
    host: &BuildTemplateHost<'_, B>,
    mapping: &[(HostNode<B>, HostNode<B>)],
    options: TemplateOptions,
) -> Result<HostEntries<B>, TemplateFailure> {
    let mut expanded_mapping: HostEntries<B> = Vec::with_capacity(mapping.len());
    for (key, item) in mapping {
        expanded_mapping.push((key.clone(), expanded(host, item, options)?));
    }
    Ok(expanded_mapping)
}

/// Every template in `value` and the containers inside it expanded, as `expanded()` does.
fn expanded<B: ConfigBuildHost>(
    host: &BuildTemplateHost<'_, B>,
    value: &ConfigNode<B::Handle>,
    options: TemplateOptions,
) -> Result<ConfigNode<B::Handle>, TemplateFailure> {
    let items = |values: &[HostNode<B>]| expanded_items(host, values, options);
    let entries = |mapping: &[(HostNode<B>, HostNode<B>)]| expanded_entries(host, mapping, options);
    match (value, value.kind()) {
        (_, NodeKind::Str) => {
            let text: &str = host.exact_text(value)?;
            if !text.contains(TEMPLATE_OPEN_TOKEN) {
                return Ok(value.clone());
            }
            Ok(match expand_template_string(host, text, options)? {
                StringExpansion::Unchanged => ConfigNode::Str(text.to_owned()),
                StringExpansion::Value(result) => result,
                StringExpansion::Text(result) => ConfigNode::Str(result),
            })
        }
        (ConfigNode::Map(mapping), _) => Ok(ConfigNode::Map(entries(mapping)?)),
        (ConfigNode::List(values), _) => Ok(ConfigNode::List(items(values)?)),
        (ConfigNode::Tuple(values), _) => Ok(ConfigNode::Tuple(items(values)?)),
        (ConfigNode::Host(opaque), kind) => match (&opaque.children, kind) {
            (HostChildren::Entries(mapping), NodeKind::Map) => {
                Ok(ConfigNode::Map(entries(mapping)?))
            }
            (HostChildren::Items(values), NodeKind::List) => Ok(ConfigNode::List(items(values)?)),
            (HostChildren::Items(values), NodeKind::Tuple) => Ok(ConfigNode::Tuple(items(values)?)),
            _ => Ok(value.clone()),
        },
        _ => Ok(value.clone()),
    }
}

/// An expansion's result and the `(kind, name)` reads it made, in order.
pub(crate) type Expanded<B> = (
    Result<ConfigNode<<B as ConfigBuildHost>::Handle>, HostHalt<B>>,
    Vec<(&'static str, String)>,
);

/// A result and the `(kind, name)` reads made on the way to it.
type Tracked<T, B> = (Result<T, HostHalt<B>>, Vec<(&'static str, String)>);

/// `expand` run with a template host over `sources`, with the reads it made.
fn with_host<B: ConfigBuildHost, T>(
    sources: ExpansionSources<'_, B>,
    scope: (bool, &str),
    expand: impl FnOnce(&BuildTemplateHost<'_, B>, TemplateOptions) -> Result<T, TemplateFailure>,
) -> Tracked<T, B> {
    let (preserve_unknown_context, label) = scope;
    let host: BuildTemplateHost<'_, B> = BuildTemplateHost {
        sources,
        label,
        reads: RefCell::new(Vec::new()),
        raised: RefCell::new(None),
    };
    let options: TemplateOptions = TemplateOptions {
        allow_context: true,
        preserve_context_tokens: false,
        preserve_unknown_context,
    };
    let result = expand(&host, options).map_err(|failure| host.halt(failure));
    (result, host.reads.into_inner())
}

/// `value` expanded, with its reads; `scope` is `preserve_unknown_context` and the context label.
pub(crate) fn expand_value<B: ConfigBuildHost>(
    sources: ExpansionSources<'_, B>,
    value: &ConfigNode<B::Handle>,
    scope: (bool, &str),
) -> Expanded<B> {
    with_host(sources, scope, |host, options| {
        expanded(host, value, options)
    })
}

/// Expanded entries and the `(kind, name)` reads the expansion made.
pub(crate) type ExpandedEntries<B> = (
    Result<HostEntries<B>, HostHalt<B>>,
    Vec<(&'static str, String)>,
);

/// A mapping's entries expanded, with the reads.
pub(crate) fn expand_entries<B: ConfigBuildHost>(
    sources: ExpansionSources<'_, B>,
    entries: &[(HostNode<B>, HostNode<B>)],
    scope: (bool, &str),
) -> ExpandedEntries<B> {
    with_host(sources, scope, |host, options| {
        expanded_entries(host, entries, options)
    })
}
