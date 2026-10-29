<script lang="ts">
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import { goto } from '$app/navigation';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import ClockIcon from '@lucide/svelte/icons/clock';
	import RadioIcon from '@lucide/svelte/icons/radio';

	type TrigType = 'schedule' | 'sensor';
	type RunStatus = 'ok' | 'fail' | 'warn' | 'none';
	type Trigger = {
		name: string;
		type: TrigType;
		job: string;
		cadence: string; // cron text or sensor condition
		next?: string; // next tick (schedules)
		enabled: boolean;
		lastTick: string; // e.g. '1 run triggered'
		lastRunId: string;
		lastRunStatus: RunStatus;
		lastRunWhen: string;
	};

	let triggers = $state<Trigger[]>([
		{ name: 'nightly_build · daily', type: 'schedule', job: 'nightly_build', cadence: 'at 02:00 UTC', next: 'Jun 6, 02:00', enabled: true, lastTick: '1 run triggered', lastRunId: 'run-9d21', lastRunStatus: 'fail', lastRunWhen: '10h ago' },
		{ name: 'activity · 15m', type: 'schedule', job: 'activity_microbatch', cadence: 'every 15m', next: 'in 6m', enabled: true, lastTick: '1 run triggered', lastRunId: 'run-1a05', lastRunStatus: 'warn', lastRunWhen: '4h ago' },
		{ name: 'revenue · daily', type: 'schedule', job: 'revenue_refresh', cadence: 'at 03:00 UTC', next: 'Jun 6, 03:00', enabled: false, lastTick: 'Paused', lastRunId: '', lastRunStatus: 'none', lastRunWhen: '—' },
		{ name: 'on_raw_orders_landed', type: 'sensor', job: 'load_sources', cadence: 'when raw__orders has new data', next: undefined, enabled: true, lastTick: '1 run triggered', lastRunId: 'run-88e1', lastRunStatus: 'ok', lastRunWhen: '3h ago' },
		{ name: 'on_payments_freshness', type: 'sensor', job: 'load_sources', cadence: 'when raw__payments stale > 1h', next: undefined, enabled: true, lastTick: 'No runs triggered', lastRunId: '', lastRunStatus: 'none', lastRunWhen: '—' },
		{ name: 'hourly_marts', type: 'schedule', job: 'marts_only', cadence: 'hourly :00', next: 'in 22m', enabled: false, lastTick: 'Paused', lastRunId: 'run-91cd', lastRunStatus: 'ok', lastRunWhen: '1h ago' }
	]);

	const runStatusColor: Record<RunStatus, string> = {
		ok: 'var(--sb-success)',
		fail: 'var(--sb-error)',
		warn: 'var(--sb-warning)',
		none: 'var(--sb-text-faint)'
	};
	const runStatusLabel: Record<RunStatus, string> = { ok: 'Success', fail: 'Failed', warn: 'Warning', none: '—' };

	let query = $state('');
	const filtered = $derived(
		triggers.filter((t) => {
			if (!query.trim()) return true;
			const q = query.toLowerCase();
			return t.name.toLowerCase().includes(q) || t.job.toLowerCase().includes(q) || t.cadence.toLowerCase().includes(q);
		})
	);

	let selected = $state<Set<string>>(new Set());
	function toggleSel(name: string) {
		const n = new Set(selected);
		n.has(name) ? n.delete(name) : n.add(name);
		selected = n;
	}
	const allSelected = $derived(filtered.length > 0 && filtered.every((t) => selected.has(t.name)));
	function toggleAll() {
		selected = allSelected ? new Set() : new Set(filtered.map((t) => t.name));
	}

	function setEnabled(name: string, on: boolean) {
		triggers = triggers.map((t) => (t.name === name ? { ...t, enabled: on } : t));
	}
	function bulkSet(on: boolean) {
		triggers = triggers.map((t) => (selected.has(t.name) ? { ...t, enabled: on, lastTick: on ? t.lastTick : 'Paused' } : t));
		selected = new Set();
	}

	const activeCount = $derived(triggers.filter((t) => t.enabled).length);
</script>

<AppTopbar title="Triggers">
	<Button variant="outline" size="sm">↻ Refresh</Button>
	<Button size="sm">+ New trigger</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder="Search triggers"
	total="{filtered.length} of {triggers.length} triggers"
	counts={[
		{ tone: 'var(--sb-success)', count: activeCount, label: 'active' },
		{ tone: 'var(--sb-text-faint)', count: triggers.length - activeCount, label: 'paused' }
	]}
>
	{#snippet filters()}
		<FilterButton label="Type" />
		<FilterButton label="Job" />
	{/snippet}
	{#snippet actions()}
		{#if selected.size}
			<span class="bulk">{selected.size} selected</span>
			<button class="bulk-btn" onclick={() => bulkSet(true)}>Enable</button>
			<button class="bulk-btn" onclick={() => bulkSet(false)}>Pause</button>
		{/if}
	{/snippet}
</ListToolbar>

<div class="sb-list-wrap">
	<table class="sb-list">
		<thead>
			<tr>
				<th class="check-col"><input type="checkbox" checked={allSelected} onchange={toggleAll} class="sb-check" aria-label="Select all" /></th>
				<th>Trigger</th>
				<th>Type</th>
				<th>Job</th>
				<th>Next tick</th>
				<th>Last tick</th>
				<th>Last run</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as t (t.name)}
				<tr class="trigger-row" class:sb-row-off={!t.enabled}>
					<td class="check-col"><input type="checkbox" checked={selected.has(t.name)} onchange={() => toggleSel(t.name)} class="sb-check" aria-label="Select {t.name}" /></td>
					<td>
						<div class="cell-name">
							<button class="sb-toggle" class:on={t.enabled} onclick={() => setEnabled(t.name, !t.enabled)} title={t.enabled ? 'Pause' : 'Enable'} aria-label="Toggle {t.name}"></button>
							<div class="min-w-0">
								<strong>{t.name}</strong>
								<div class="cell-desc">{t.cadence}</div>
							</div>
						</div>
					</td>
					<td>
						<span class="type-cell">
							{#if t.type === 'schedule'}<ClockIcon size={14} />{:else}<RadioIcon size={14} />{/if}
							{t.type === 'schedule' ? 'Schedule' : 'Sensor'}
						</span>
					</td>
					<td><a class="link" href="/jobs/{t.job}">{t.job}</a></td>
					<td class="muted">{t.type === 'schedule' && t.next ? (t.enabled ? t.next : 'Paused') : '—'}</td>
					<td class="muted">{t.lastTick}</td>
					<td>
						{#if t.lastRunId}
							<a href="/runs/{t.lastRunId}" class="last-run">
								<StatusLabel tone={runStatusColor[t.lastRunStatus]} label={runStatusLabel[t.lastRunStatus]} />
								<RelativeTime value={t.lastRunWhen} />
							</a>
						{:else}
							<span class="muted">—</span>
						{/if}
					</td>
				</tr>
			{:else}
				<tr><td colspan="7" class="empty">No triggers match the filter.</td></tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.check-col {
		width: 44px;
	}
	:global(.sb-list tbody tr.trigger-row) {
		cursor: default;
	}
	.type-cell {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		color: var(--muted-foreground);
	}
	.last-run {
		display: inline-flex;
		align-items: center;
		gap: 10px;
	}
	.bulk {
		margin-left: 8px;
		color: var(--muted-foreground);
		font-size: 12.5px;
	}
	.bulk-btn {
		height: 28px;
		padding: 0 10px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: transparent;
		font-size: 12.5px;
	}
	.bulk-btn:hover {
		background: var(--sb-hover);
	}
</style>
