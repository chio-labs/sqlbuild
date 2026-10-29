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
	import LoadRow from '$lib/components/list/load-row.svelte';
	import type { CheckOutcome, RunScopePhase } from '$lib/api';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { checkOutcomeLabel as resultLabel, checkOutcomeTone as resultColor } from '$lib/status';

	type Result = 'pass' | 'warn' | 'fail';
	const outcome = (c: { latest: { outcome: CheckOutcome } | null }): CheckOutcome => c.latest?.outcome ?? 'skipped';

	const checks = createResource((client, scope) => client.listChecks(scope), ['checks', 'runs']);
	const all = $derived(checks.data ?? []);

	const phaseLabel: Record<RunScopePhase, string> = { delta_and_final: 'Delta and final', final: 'Final' };

	let query = $state('');
	let resultFilter = $state<'all' | Result>('all');
	const resultFilters: ('all' | Result)[] = ['all', 'fail', 'warn', 'pass'];
	const resultFilterLabel: Record<'all' | Result, string> = { all: 'All', fail: 'Failing', warn: 'Warning', pass: 'Passing' };

	const filtered = $derived(
		all.filter((c) => {
			if (resultFilter !== 'all' && outcome(c) !== resultFilter) return false;
			if (query.trim()) {
				const q = query.toLowerCase();
				return c.name.toLowerCase().includes(q) || (c.node ?? '').toLowerCase().includes(q) || (c.definition ?? c.kind).toLowerCase().includes(q);
			}
			return true;
		})
	);

	const counts = $derived({
		total: all.length,
		pass: all.filter((c) => outcome(c) === 'pass').length,
		fail: all.filter((c) => outcome(c) === 'fail' || outcome(c) === 'error').length,
		warn: all.filter((c) => outcome(c) === 'warn').length
	});
</script>

<AppTopbar title="Checks">
	<Button variant="outline" size="sm" onclick={() => checks.refresh()}>↻ Refresh</Button>
	<Button size="sm" disabled={!app.can('run.adhoc')} title={app.can('run.adhoc') ? undefined : 'Requires run.adhoc'}>▷ Run checks</Button>
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
				<th>Run scope</th>
				<th>Detail</th>
				<th>When</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as c (c.name + (c.node ?? ''))}
				<tr onclick={() => c.latest?.runId && goto(`/runs/${c.latest.runId}`)}>
					<td>
						<div class="cell-name">
							<ShieldCheckIcon size={15} strokeWidth={1.75} />
							<code class="check-name">{c.name}</code>
						</div>
					</td>
					<td><StatusLabel tone={resultColor[outcome(c)]} label={resultLabel[outcome(c)]} /></td>
					<td>{#if c.node === null}<span class="muted">Standalone</span>{:else}<a href="/catalog/{c.node}" class="link" onclick={(e) => e.stopPropagation()}>{c.node}</a>{/if}</td>
					<td class="muted">{c.definition ?? c.kind}</td>
					<td class="muted capitalize">{c.severity}</td>
					<td class="muted">{phaseLabel[c.runScopePhase]}</td>
					<td style:color={outcome(c) === 'fail' ? 'var(--sb-error)' : outcome(c) === 'warn' ? 'var(--sb-warning)' : 'var(--muted-foreground)'}>{c.latest?.violationCount ?? c.latest?.measuredValue ?? '—'}</td>
					<td><RelativeTime value={formatAgo(c.latest?.evaluatedAt, app.now)} exact={formatStamp(c.latest?.evaluatedAt)} /></td>
				</tr>
			{:else}
				<LoadRow colspan={8} resource={checks} empty={all.length ? 'No checks match the filter.' : 'No checks are defined in this snapshot.'} />
			{/each}
		</tbody>
	</table>
</div>

<style>
	.check-name {
		color: var(--foreground);
	}
</style>
