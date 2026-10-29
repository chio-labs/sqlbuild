<script lang="ts">
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import SegmentedFilter from '$lib/components/list/segmented-filter.svelte';
	import RunTimeline from '$lib/components/timeline/run-timeline.svelte';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import { formatAgo, formatDuration, formatStamp } from '$lib/format/time';
	import { formatNodeCounts, isActiveRun, isProblemRun, runKindLabel, runStatusLabel, runStatusTone } from '$lib/status';

	const runs = createResource((client, scope) => client.listRuns(scope), ['runs']);

	let query = $state('');
	let view = $state<'list' | 'timeline'>(page.url.searchParams.get('view') === 'timeline' ? 'timeline' : 'list');
	$effect(() => {
		const url = new URL(window.location.href);
		if (view === 'timeline') url.searchParams.set('view', 'timeline');
		else url.searchParams.delete('view');
		if (url.href !== window.location.href) goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	});

	const all = $derived(runs.data ?? []);

	// Live runs first, then most recently queued.
	const sortedRuns = $derived(
		all
			.filter((r) => {
				const q = query.trim().toLowerCase();
				return !q || `${r.id} ${r.jobKey ?? ''} ${r.requestedBy.name}`.toLowerCase().includes(q);
			})
			.sort((a, b) => {
				const live = Number(isActiveRun(b.status)) - Number(isActiveRun(a.status));
				return live || b.queuedAt.localeCompare(a.queuedAt);
			})
	);
	const activeCount = $derived(all.filter((r) => isActiveRun(r.status)).length);
	const problemCount = $derived(all.filter((r) => isProblemRun(r.status)).length);
</script>

<AppTopbar title="Runs">
	<Button variant="outline" size="sm" onclick={() => runs.refresh()}>↻ Refresh</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder={view === 'timeline' ? 'Search jobs' : 'Search runs'}
	total={view === 'timeline' ? 'Timeline' : `${all.length} runs`}
	counts={view === 'timeline'
		? []
		: [
				{ tone: 'var(--sb-running)', count: activeCount, label: 'active' },
				{ tone: 'var(--sb-error)', count: problemCount, label: 'failed or partial' }
			]}
>
	{#snippet filters()}
		<SegmentedFilter bind:value={view} options={[{ value: 'list', label: 'List' }, { value: 'timeline', label: 'Timeline' }]} />
		<FilterButton label="Status" />
		<FilterButton label="Job" />
		<FilterButton label="Kind" />
		{#if view === 'list'}<FilterButton label="Time" value="Last 24h" />{/if}
	{/snippet}
</ListToolbar>

{#if view === 'timeline'}
	<div class="timeline-page"><RunTimeline bind:query showSearch={false} /></div>
{:else}
	<div class="sb-list-wrap">
		<table class="sb-list">
			<thead>
				<tr>
					<th>Run</th>
					<th>Job</th>
					<th>Kind</th>
					<th>Nodes</th>
					<th>Started</th>
					<th class="num">Duration</th>
					<th>By</th>
				</tr>
			</thead>
			<tbody>
				{#each sortedRuns as r (r.id)}
					<tr onclick={() => goto(`/runs/${r.id}`)} title={r.statusReason ?? undefined}>
						<td>
							<div class="run-cell">
								<StatusLabel tone={runStatusTone[r.status]} label={runStatusLabel[r.status]} />
								<a class="code muted" href="/runs/{r.id}" onclick={(e) => e.stopPropagation()}>{r.id}</a>
							</div>
						</td>
						<td>
							{#if r.jobKey}
								<a class="link" href="/jobs/{r.jobKey}" onclick={(e) => e.stopPropagation()}>{r.jobKey}</a>
							{:else}
								<span class="muted">Ad hoc selection</span>
							{/if}
						</td>
						<td class="muted">{runKindLabel[r.kind]}</td>
						<td class="muted">{formatNodeCounts(r.nodeCounts)}</td>
						<td>
							{#if r.startedAt}
								<RelativeTime value={formatAgo(r.startedAt, app.now)} exact={formatStamp(r.startedAt)} />
							{:else}
								<span class="muted">Queued {formatAgo(r.queuedAt, app.now)}</span>
							{/if}
						</td>
						<td class="num muted">{r.startedAt ? formatDuration(r.startedAt, r.endedAt, app.now) : '—'}</td>
						<td class="muted">{r.requestedBy.name}</td>
					</tr>
				{:else}
					<LoadRow colspan={7} resource={runs} empty={all.length ? 'No runs match the filter.' : 'No runs yet for this target.'} />
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	.timeline-page {
		display: flex;
		min-height: 0;
		flex: 1;
		flex-direction: column;
	}
	.run-cell {
		display: grid;
		grid-template-columns: 124px auto;
		align-items: center;
		gap: 10px;
	}
</style>
