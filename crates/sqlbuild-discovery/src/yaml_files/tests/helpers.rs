use crate::yaml_files::models::YamlFileOutcome;

/// An expected "Python loads the contents" outcome; only its variant is compared.
pub(super) fn python() -> YamlFileOutcome {
    YamlFileOutcome::LoadInPython {
        contents: String::new(),
    }
}
