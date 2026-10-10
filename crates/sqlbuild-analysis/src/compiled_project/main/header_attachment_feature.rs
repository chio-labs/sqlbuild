use crate::compiled_project::models::AttachmentFeature;

/// The header feature among the config `keys` the attachment still finishes, earliest first.
pub fn header_attachment_feature(keys: &[String]) -> Option<AttachmentFeature> {
    crate::compiled_project::_helpers::plain::header_attachment_feature(keys)
}
