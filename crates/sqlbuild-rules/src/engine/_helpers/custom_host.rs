use crate::models::CustomHostSpec;
use fensu_policy::lifecycle::models::{
    CustomHostInvocation, CustomHostOutputLimits, CustomHostRequest,
};
use fensu_policy::run_custom_host;
use std::path::Path;
use std::time::Duration;

pub(crate) fn run_custom_host_json(spec_json: &str) -> Result<String, String> {
    let spec: CustomHostSpec = serde_json::from_str(spec_json)
        .map_err(|error| format!("invalid custom host request: {error}"))?;
    let request = CustomHostRequest {
        protocol: fensu_policy::lifecycle::constants::CUSTOM_HOST_PROTOCOL_VERSION,
        runtime_version: spec.runtime_version.clone(),
        payload: spec.payload,
    };
    let response = run_custom_host::<_, serde_json::Value>(CustomHostInvocation {
        program: Path::new(&spec.program),
        arguments: &spec.arguments,
        timeout: Duration::from_millis(spec.timeout_millis),
        output_limits: CustomHostOutputLimits::default(),
        request: &request,
    })
    .map_err(|error| format!("invalid rules lifecycle: {error}"))?;
    let payload = response.payload.ok_or_else(|| {
        "custom rule host returned no payload after successful validation".to_owned()
    })?;
    serde_json::to_string(&payload).map_err(|error| error.to_string())
}
