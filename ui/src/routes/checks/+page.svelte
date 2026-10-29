<script lang="ts">
	import ShieldCheckIcon from '@lucide/svelte/icons/shield-check';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import SegmentedFilter from '$lib/components/list/segmented-filter.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import { goto } from '$app/navigation';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';

	type Result = 'pass' | 'fail' | 'warn';
	type Severity = 'error' | 'warn';
	type Phase = 'pre-promotion' | 'delta-phase' | 'standalone';
	type Check = {
		name: string; // audit expression / name
		model: string; // attached model (or '—' for standalone)
		type: string; // not_null / unique / relationships / expression_is_true / accepted_values
		severity: Severity;
		phase: Phase;
		result: Result;
		detail: string; // e.g. '0 rows' / '7 rows violated' / 'blocked promotion'
		lastRunId: string;
		when: string;
	};

	const checks: Check[] = [
		{ name: 'not_null(order_id)', model: 'fact_orders', type: 'not_null', severity: 'error', phase: 'pre-promotion', result: 'pass', detail: '0 rows', lastRunId: 'run-9d21', when: '14m ago' },
		{ name: 'unique(order_id)', model: 'fact_orders', type: 'unique', severity: 'error', phase: 'pre-promotion', result: 'pass', detail: '0 rows', lastRunId: 'run-9d21', when: '14m ago' },
		{ name: 'relationships(customer_id → dim_customers)', model: 'fact_orders', type: 'relationships', severity: 'error', phase: 'pre-promotion', result: 'pass', detail: '0 orphans', lastRunId: 'run-9d21', when: '14m ago' },
		{ name: 'not_null(customer_id)', model: 'stg_customers', type: 'not_null', severity: 'error', phase: 'pre-promotion', result: 'pass', detail: '0 rows', lastRunId: 'run-9d21', when: '14m ago' },
		{ name: 'not_null(payment_id)', model: 'stg_payments', type: 'not_null', severity: 'warn', phase: 'pre-promotion', result: 'warn', detail: '2 nulls', lastRunId: 'run-9d21', when: '14m ago' },
		{ name: 'accepted_values(order_status)', model: 'stg_orders', type: 'accepted_values', severity: 'error', phase: 'pre-promotion', result: 'pass', detail: '0 rows', lastRunId: 'run-9d21', when: '14m ago' },
		{ name: 'expression_is_true(activity_hour IS NOT NULL)', model: 'hourly_activity_ctx', type: 'expression_is_true', severity: 'error', phase: 'delta-phase', result: 'fail', detail: '7 rows · blocked promotion', lastRunId: 'run-9d21', when: '14m ago' },
		{ name: 'unique(activity_hour)', model: 'daily_activity', type: 'unique', severity: 'error', phase: 'pre-promotion', result: 'pass', detail: '0 rows', lastRunId: 'run-2b70', when: '3h ago' },
		{ name: 'revenue reconciles to source', model: '—', type: 'standalone', severity: 'error', phase: 'standalone', result: 'pass', detail: 'within 0.1%', lastRunId: 'run-c40e', when: '18h ago' }
	];

	const resultColor: Record<Result, string> = { pass: 'var(--sb-success)', fail: 'var(--sb-error)', warn: 'var(--sb-warning)' };
	const resultLabel: Record<Result, string> = { pass: 'Passed', fail: 'Failed', warn: 'Warning' };

	let query = $state('');
	let resultFilter = $state<'all' | Result>('all');
	const resultFilters: ('all' | Result)[] = ['all', 'fail', 'warn', 'pass'];
	const resultFilterLabel: Record<'all' | Result, string> = { all: 'All', fail: 'Failing', warn: 'Warning', pass: 'Passing' };

	const filtered = $derived(
		checks.filter((c) => {
			if (resultFilter !== 'all' && c.result !== resultFilter) return false;
			if (query.trim()) {
				const q = query.toLowerCase();
				return c.name.toLowerCase().includes(q) || c.model.toLowerCase().includes(q) || c.type.toLowerCase().includes(q);
			}
			return true;
		})
	);

	const counts = $derived({
		total: checks.length,
		pass: checks.filter((c) => c.result === 'pass').length,
		fail: checks.filter((c) => c.result === 'fail').length,
		warn: checks.filter((c) => c.result === 'warn').length
	});
</script>

<AppTopbar title="Checks">
	<Button variant="outline" size="sm">↻ Refresh</Button>
	<Button size="sm">▷ Run checks</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder="Search checks"
	total="{counts.pass} of {counts.total} passing"
	counts={[
		{ tone: 'var(--sb-warning)', count: counts.warn, label: 'warning' },
		{ tone: 'var(--sb-error)', count: counts.fail, label: 'failing' }
	]}
>
	{#snippet filters()}
		<SegmentedFilter
			bind:value={resultFilter}
			options={resultFilters.map((f) => ({ value: f, label: resultFilterLabel[f], count: f === 'all' ? counts.total : counts[f] }))}
		/>
		<FilterButton label="Model" />
		<FilterButton label="Type" />
	{/snippet}
</ListToolbar>

<div class="sb-list-wrap">
	<table class="sb-list">
		<thead>
			<tr>
				<th>Check</th>
				<th>Result</th>
				<th>Model</th>
				<th>Type</th>
				<th>Severity</th>
				<th>Phase</th>
				<th>Detail</th>
				<th>When</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as c (c.name + c.model)}
				<tr onclick={() => goto(`/runs/${c.lastRunId}`)}>
					<td>
						<div class="cell-name">
							<ShieldCheckIcon size={15} strokeWidth={1.75} />
							<code class="check-name">{c.name}</code>
						</div>
					</td>
					<td><StatusLabel tone={resultColor[c.result]} label={resultLabel[c.result]} /></td>
					<td>{#if c.model === '—'}<span class="muted">Standalone</span>{:else}<a href="/catalog/{c.model}" class="link" onclick={(e) => e.stopPropagation()}>{c.model}</a>{/if}</td>
					<td class="muted">{c.type}</td>
					<td class="muted capitalize">{c.severity}</td>
					<td class="muted">{c.phase}</td>
					<td style:color={c.result === 'fail' ? 'var(--sb-error)' : c.result === 'warn' ? 'var(--sb-warning)' : 'var(--muted-foreground)'}>{c.detail}</td>
					<td><RelativeTime value={c.when} /></td>
				</tr>
			{:else}
				<tr><td colspan="8" class="empty">No checks match the filter.</td></tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.check-name {
		color: var(--foreground);
	}
</style>
