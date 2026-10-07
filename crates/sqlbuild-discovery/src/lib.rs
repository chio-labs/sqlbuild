//! Native project discovery: the directory walk, file facts and parsing of authored files.

#![forbid(unsafe_code)]

pub(crate) mod _helpers;
pub mod constants;
pub mod declarations;
pub mod model_files;
pub mod models;
pub mod tree;
