//! Python's resource assembly facts for one project, up to the resource Python raises at.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::assembly::project::_helpers::resources::project_resources;
use crate::assembly::project::models::{ProjectRequest, ProjectResources};

/// Each resource's facts up to the first resource Python raises at; Err is a native failure.
pub fn assemble_project_resources(request: &ProjectRequest) -> Result<ProjectResources, String> {
    catch_compiler_panic(|| Ok(project_resources(request)))
}
