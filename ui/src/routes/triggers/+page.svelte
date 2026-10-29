<script lang="ts">
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import ClockIcon from '@lucide/svelte/icons/clock';
	import RadioIcon from '@lucide/svelte/icons/radio';
	import type { Trigger, TriggerState } from '$lib/api';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import { formatAgo, formatIn, formatStamp } from '$lib/format/time';
	import { runStatusLabel, runStatusTone, tickOutcomeLabel } from '$lib/status';

	const triggers = createResource((client, scope) => client.listTriggers(scope), ['triggers', 'ticks']);
	const canToggle = $derived(app.can('trigger.toggle'));
	let actionError = $state<string | null>(null);

	let query = $state('');
	const all = $derived(triggers.data ?? []);
	const filtered = $derived(
		all.filter((t) => {
			if (!query.trim()) return true;
			const q = query.toLowerCase();
			return t.name.toLowerCase().includes(q) || (t.jobKey ?? '').toLowerCase().includes(q) || t.cadence.toLowerCase().includes(q);
		})
	);

	let selected = $state<Set<string>>(new Set());
	function toggleSel(name: string) {
		const n = new Set(selected);
		if (n.has(name)) n.delete(name);
		else n.add(name);
		selected = n;
	}
	const allSelected = $derived(filtered.length > 0 && filtered.every((t) => selected.has(t.name)));
	function toggleAll() {
		selected = allSelected ? new Set() : new Set(filtered.map((t) => t.name));
	}

	async function setState(names: string[], state: TriggerState) {
		const scope = app.scope;
		if (!scope) return;
		actionError = null;
		try {
			await app.client.setTriggerStates(scope, names, state);
		} catch (error) {
			actionError = error instanceof Error ? error.message : String(error);
		}
	}
	function bulkSet(state: TriggerState) {
		void setState([...selected], state);
		selected = new Set();
	}

	const runningCount = $derived(all.filter((t) => t.state === 'running').length);

	function nextTick(t: Trigger): string {
		if (t.type === 'sensor') return '—';
		if (t.state === 'paused') return 'Paused';
		if (!t.nextDueAt) return '—';
		if (Date.parse(t.nextDueAt) < app.now) return `Overdue, due ${formatAgo(t.nextDueAt, app.now)}`;
		return formatIn(t.nextDueAt, app.now);
	}
</script>

<AppTopbar title="Triggers">
	<Button variant="outline" size="sm" onclick={() => triggers.refresh()}>↻ Refresh</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder="Search triggers"
	total="{filtered.length} of {all.length} triggers"
	counts={[
		{ tone: 'var(--sb-success)', count: runningCount, label: 'running' },
		{ tone: 'var(--sb-text-faint)', count: all.length - runningCount, label: 'paused' }
	]}
>
	{#snippet filters()}
		<FilterButton label="Type" />
		<FilterButton label="Job" />
	{/snippet}
	{#snippet actions()}
		{#if selected.size && canToggle}
			<span class="bulk">{selected.size} selected</span>
			<button class="bulk-btn" onclick={() => bulkSet('running')}>Resume</button>
			<button class="bulk-btn" onclick={() => bulkSet('paused')}>Pause</button>
		{/if}
		{#if actionError}<span class="bulk error">{actionError}</span>{/if}
	{/snippet}
</ListToolbar>

<div class="sb-list-wrap">
	<table class="sb-list">
		<thead>
			<tr>
				<th class="check-col">
					<input type="checkbox" checked={allSelected} onchange={toggleAll} class="sb-check" aria-label="Select all" disabled={!canToggle} />
				</th>
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
				<tr class="trigger-row" class:sb-row-off={t.state === 'paused'}>
					<td class="check-col">
						<input type="checkbox" checked={selected.has(t.name)} onchange={() => toggleSel(t.name)} class="sb-check" aria-label="Select {t.name}" disabled={!canToggle} />
					</td>
					<td>
						<div class="cell-name">
							<button
								class="sb-toggle"
								class:on={t.state === 'running'}
								disabled={!canToggle}
								onclick={() => setState([t.name], t.state === 'running' ? 'paused' : 'running')}
								title={canToggle ? (t.state === 'running' ? 'Pause' : 'Resume') : 'Requires trigger.toggle'}
								aria-label="Toggle {t.name}"
							></button>
							<div class="min-w-0">
								<strong>{t.name}</strong>
								<div class="cell-desc">
									{t.cadence}
									{#if t.state !== t.defaultState}<span class="override" title="Differs from the state declared in code">· {t.state} (code default: {t.defaultState})</span>{/if}
								</div>
							</div>
						</div>
					</td>
					<td>
						<span class="type-cell">
							{#if t.type === 'schedule'}<ClockIcon size={14} />{:else}<RadioIcon size={14} />{/if}
							{t.type === 'schedule' ? 'Schedule' : 'Sensor'}
						</span>
					</td>
					<td><a class="link" href="/jobs/{t.jobKey}">{t.jobKey}</a></td>
					<td class="muted">{nextTick(t)}</td>
					<td class="muted" title={t.lastTick?.reason ?? undefined}>
						{#if t.lastTick}
							{tickOutcomeLabel[t.lastTick.outcome]}
							{#if t.lastTick.coveredByRunId}<a class="link" href="/runs/{t.lastTick.coveredByRunId}">{t.lastTick.coveredByRunId}</a>{/if}
						{:else}
							No ticks yet
						{/if}
					</td>
					<td>
						{#if t.lastRun}
							<a href="/runs/{t.lastRun.id}" class="last-run">
								<StatusLabel tone={runStatusTone[t.lastRun.status]} label={runStatusLabel[t.lastRun.status]} />
								<RelativeTime value={formatAgo(t.lastRun.startedAt, app.now)} exact={formatStamp(t.lastRun.startedAt)} />
							</a>
						{:else}
							<span class="muted">—</span>
						{/if}
					</td>
				</tr>
			{:else}
				<LoadRow colspan={7} resource={triggers} empty={all.length ? 'No triggers match the filter.' : 'No triggers are defined in this snapshot.'} />
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
	.override {
		color: var(--sb-warning);
	}
	.bulk {
		margin-left: 8px;
		color: var(--muted-foreground);
		font-size: 12.5px;
	}
	.bulk.error {
		color: var(--sb-error);
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
