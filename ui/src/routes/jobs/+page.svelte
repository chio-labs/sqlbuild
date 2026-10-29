<script lang="ts">
	import WorkflowIcon from '@lucide/svelte/icons/workflow';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import { goto } from '$app/navigation';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';

	type Status = 'ok' | 'fail' | 'warn' | 'never';
	type Job = {
		name: string;
		desc: string;
		select: string; // the --select expression
		nodes: number;
		schedule: string; // human cadence or 'manual'
		enabled: boolean; // schedule on/off (manual jobs have no schedule to toggle)
		lastStatus: Status;
		lastRun: string;
		lastRunId: string;
	};

	// Jobs = named --select groupings (CLI-level selection + settings).
	let jobs = $state<Job[]>([
		{ name: 'nightly_build', desc: 'Full project build', select: '+', nodes: 16, schedule: 'daily 02:00', enabled: true, lastStatus: 'fail', lastRun: '14m ago', lastRunId: 'run-9d21' },
		{ name: 'marts_only', desc: 'Marts and their upstreams', select: '+marts', nodes: 9, schedule: 'manual', enabled: false, lastStatus: 'ok', lastRun: '1h ago', lastRunId: 'run-91cd' },
		{ name: 'load_sources', desc: 'Ingest loaders + sources', select: 'tag:ingest', nodes: 3, schedule: 'hourly', enabled: true, lastStatus: 'ok', lastRun: '3h ago', lastRunId: 'run-88e1' },
		{ name: 'checks_only', desc: 'Run audits across all models', select: '* --checks-only', nodes: 14, schedule: 'manual', enabled: false, lastStatus: 'ok', lastRun: '18h ago', lastRunId: 'run-c40e' },
		{ name: 'activity_microbatch', desc: 'Incremental activity models', select: '+hourly_activity_ctx', nodes: 5, schedule: 'every 15m', enabled: true, lastStatus: 'warn', lastRun: '4h ago', lastRunId: 'run-1a05' },
		{ name: 'revenue_refresh', desc: 'Daily revenue + downstream BI', select: 'daily_revenue+', nodes: 4, schedule: 'daily 03:00', enabled: false, lastStatus: 'never', lastRun: '—', lastRunId: '' }
	]);

	function toggleSchedule(name: string) {
		jobs = jobs.map((j) => (j.name === name ? { ...j, enabled: !j.enabled } : j));
	}

	const statusColor: Record<Status, string> = {
		ok: 'var(--sb-success)',
		fail: 'var(--sb-error)',
		warn: 'var(--sb-warning)',
		never: 'var(--sb-text-faint)'
	};
	const statusLabel: Record<Status, string> = { ok: 'Success', fail: 'Failed', warn: 'Warning', never: 'Never run' };

	let query = $state('');
	const filtered = $derived(
		jobs.filter((j) => {
			if (!query.trim()) return true;
			const q = query.toLowerCase();
			return j.name.toLowerCase().includes(q) || j.desc.toLowerCase().includes(q) || j.select.toLowerCase().includes(q);
		})
	);
</script>

<AppTopbar title="Jobs">
	<Button variant="outline" size="sm">↻ Refresh</Button>
	<Button size="sm">+ New job</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder="Search jobs"
	total="{filtered.length} of {jobs.length} jobs"
	counts={[
		{ tone: 'var(--sb-success)', count: jobs.filter((j) => j.enabled).length, label: 'scheduled' },
		{ tone: 'var(--sb-error)', count: jobs.filter((j) => j.lastStatus === 'fail').length, label: 'failing' }
	]}
>
	{#snippet filters()}
		<FilterButton label="Schedule" />
		<FilterButton label="Last run" />
	{/snippet}
</ListToolbar>

<div class="sb-list-wrap">
	<table class="sb-list">
		<thead>
			<tr>
				<th>Job</th>
				<th>Selector</th>
				<th class="num">Nodes</th>
				<th>Schedule</th>
				<th>Last run</th>
				<th>When</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as j (j.name)}
				<tr onclick={() => goto(`/jobs/${j.name}`)}>
					<td>
						<div class="cell-name">
							<WorkflowIcon size={15} strokeWidth={1.75} />
							<div class="min-w-0">
								<a href="/jobs/{j.name}" onclick={(e) => e.stopPropagation()}>{j.name}</a>
								<div class="cell-desc">{j.desc}</div>
							</div>
						</div>
					</td>
					<td><code>{j.select}</code></td>
					<td class="num muted">{j.nodes}</td>
					<td>
						{#if j.schedule === 'manual'}
							<span class="muted">Manual</span>
						{:else}
							<div class="flex items-center gap-2.5">
								<button
									class="sb-toggle"
									class:on={j.enabled}
									onclick={(e) => {
										e.stopPropagation();
										toggleSchedule(j.name);
									}}
									title={j.enabled ? 'Pause schedule' : 'Enable schedule'}
									aria-label="Toggle schedule for {j.name}"
								></button>
								<span class:muted={!j.enabled}>{j.schedule}</span>
							</div>
						{/if}
					</td>
					<td>
						{#if j.lastStatus === 'never'}
							<span class="muted">Never run</span>
						{:else}
							<StatusLabel tone={statusColor[j.lastStatus]} label={statusLabel[j.lastStatus]} />
						{/if}
					</td>
					<td><RelativeTime value={j.lastRun} /></td>
				</tr>
			{:else}
				<tr><td colspan="6" class="empty">No jobs match the filter.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
