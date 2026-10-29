<script lang="ts">
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import SegmentedFilter from '$lib/components/list/segmented-filter.svelte';
	import RunTimeline from '$lib/components/timeline/run-timeline.svelte';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';

	type RunStatus = 'ok' | 'fail' | 'warn' | 'running';
	type Run = {
		id: string;
		job: string;
		trigger: 'schedule' | 'manual' | 'sensor';
		env: string;
		status: RunStatus;
		started: string;
		duration: string;
		by: string;
		nodes: string;
		ago: string;
	};

	let query = $state('');
	let view = $state<'list' | 'timeline'>(page.url.searchParams.get('view') === 'timeline' ? 'timeline' : 'list');
	$effect(() => {
		const url = new URL(window.location.href);
		if (view === 'timeline') url.searchParams.set('view', 'timeline');
		else url.searchParams.delete('view');
		if (url.href !== window.location.href) goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	});

	const runs: Run[] = [
		{ id: 'run-4f2a', job: 'nightly_build', trigger: 'schedule', env: 'prod', status: 'fail', started: '2026-05-31 11:46', duration: '1.4s', by: '@scheduler', nodes: '8 ok · 1 warn · 1 fail · 3 skip', ago: '14m ago' },
		{ id: 'run-91cd', job: 'marts_only', trigger: 'manual', env: 'prod', status: 'ok', started: '2026-05-31 10:31', duration: '0.9s', by: '@analytics', nodes: '6 ok', ago: '1h ago' },
		{ id: 'run-2b70', job: 'nightly_build', trigger: 'schedule', env: 'prod', status: 'ok', started: '2026-05-31 09:00', duration: '1.1s', by: '@scheduler', nodes: '12 ok', ago: '3h ago' },
		{ id: 'run-88e1', job: 'load_sources', trigger: 'sensor', env: 'prod', status: 'ok', started: '2026-05-31 08:42', duration: '0.3s', by: '@sensor', nodes: '2 ok', ago: '3h ago' },
		{ id: 'run-1a05', job: 'nightly_build', trigger: 'schedule', env: 'prod', status: 'warn', started: '2026-05-31 08:00', duration: '1.2s', by: '@scheduler', nodes: '11 ok · 1 warn', ago: '4h ago' },
		{ id: 'run-77b3', job: 'nightly_build', trigger: 'schedule', env: 'prod', status: 'ok', started: '2026-05-31 06:00', duration: '2.1s', by: '@scheduler', nodes: '12 ok', ago: '6h ago' },
		{ id: 'run-c40e', job: 'checks_only', trigger: 'manual', env: 'prod', status: 'ok', started: '2026-05-30 18:12', duration: '0.5s', by: '@analytics', nodes: '14 checks', ago: '18h ago' },
		{ id: 'run-9d21', job: 'nightly_build', trigger: 'schedule', env: 'prod', status: 'running', started: '2026-05-31 12:00', duration: '—', by: '@scheduler', nodes: '4/12 running', ago: 'just now' }
	];

	const statusColor: Record<RunStatus, string> = {
		ok: 'var(--sb-success)',
		fail: 'var(--sb-error)',
		warn: 'var(--sb-warning)',
		running: 'var(--sb-running)'
	};
	const statusLabel: Record<RunStatus, string> = {
		ok: 'Success',
		fail: 'Failed',
		warn: 'Warning',
		running: 'Running'
	};

	// running runs first, then most recently started.
	const sortedRuns = $derived(
		[...runs]
			.filter((r) => !query.trim() || `${r.id} ${r.job} ${r.by}`.toLowerCase().includes(query.trim().toLowerCase()))
			.sort((a, b) => {
			if (a.status === 'running' && b.status !== 'running') return -1;
			if (b.status === 'running' && a.status !== 'running') return 1;
			return b.started.localeCompare(a.started);
		})
	);
</script>

<AppTopbar title="Runs">
	<Button variant="outline" size="sm">↻ Refresh</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder={view === 'timeline' ? 'Search jobs' : 'Search runs'}
	total={view === 'timeline' ? '14 jobs' : `${runs.length} runs`}
	counts={view === 'timeline' ? [] : [
		{ tone: 'var(--sb-running)', count: runs.filter((r) => r.status === 'running').length, label: 'running' },
		{ tone: 'var(--sb-error)', count: runs.filter((r) => r.status === 'fail').length, label: 'failed' }
	]}
>
	{#snippet filters()}
		<SegmentedFilter bind:value={view} options={[{ value: 'list', label: 'List' }, { value: 'timeline', label: 'Timeline' }]} />
		<FilterButton label="Status" />
		<FilterButton label="Job" />
		<FilterButton label="Trigger" />
		<FilterButton label="Env" />
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
				<th>Trigger</th>
				<th>Env</th>
				<th>Nodes</th>
				<th>Started</th>
				<th class="num">Duration</th>
				<th>By</th>
			</tr>
		</thead>
		<tbody>
			{#each sortedRuns as r (r.id)}
				<tr onclick={() => goto(`/runs/${r.id}`)}>
					<td>
						<div class="run-cell">
							<StatusLabel tone={statusColor[r.status]} label={statusLabel[r.status]} />
							<a class="code muted" href="/runs/{r.id}" onclick={(e) => e.stopPropagation()}>{r.id}</a>
						</div>
					</td>
					<td><a class="link" href="/jobs/{r.job}" onclick={(e) => e.stopPropagation()}>{r.job}</a></td>
					<td class="muted">{r.trigger}</td>
					<td><span class="sb-tag">{r.env}</span></td>
					<td class="muted">{r.nodes}</td>
					<td><RelativeTime value={r.ago} exact={r.started} /></td>
					<td class="num muted">{r.duration}</td>
					<td class="muted">{r.by}</td>
				</tr>
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
		grid-template-columns: 92px auto;
		align-items: center;
		gap: 10px;
	}
</style>
