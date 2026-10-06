use std::path::Path;

pub fn load_config_json(project_dir: &Path) -> Result<String, String> {
    crate::configuration::_helpers::loading::load_config_json(project_dir)
}
