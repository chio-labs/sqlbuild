pub(crate) fn analyze_cte_slots_batch_json(payload: &str) -> Result<String, String> {
    crate::query_analysis::cte_usage::analyze_batch(payload)
}
