<script lang="ts">
	import EyeIcon from '@lucide/svelte/icons/eye';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import SegmentedFilter from '$lib/components/list/segmented-filter.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import NoAccess from '$lib/components/platform/no-access.svelte';
	import { CAPABILITIES, type AuditOutcome } from '$lib/api';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { formatAssignmentScope } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';

	let actor = $state('');
	let action = $state('');
	let outcome = $state<AuditOutcome | 'any'>('any');
	let evidenceOnly = $state(false);

	const entries = createResource((client) => {
		const query = { actor: actor || undefined, action: action || undefined, outcome: outcome === 'any' ? undefined : outcome, evidenceOnly, limit: 500 };
		return app.can('audit.view') ? client.listAuditEntries(query) : Promise.resolve([]);
	});
	// Unfiltered once, for the actor list.
	const everyone = createResource((client) => (app.can('audit.view') ? client.listAuditEntries({ limit: 500 }) : Promise.resolve([])));

	const actors = $derived([...new Set((everyone.data ?? []).map((e) => e.actor.name))].sort());
	const actions = [...CAPABILITIES, 'role.approve', 'role.reject', 'session.login'];
	const rows = $derived(entries.data ?? []);
	const locations = $derived(app.bootstrap?.locations ?? []);
</script>

<AppTopbar title="Audit log">
	<Button
		variant="outline"
		size="sm"
		onclick={() => {
			entries.refresh();
			everyone.refresh();
		}}>↻ Refresh</Button
	>
</AppTopbar>

{#if !app.can('audit.view')}
	<NoAccess what="the audit log" requires="audit.view" />
{:else}
	<div class="toolbar">
		<select class="field" bind:value={actor} aria-label="Actor">
			<option value="">Any actor</option>
			{#each actors as a (a)}<option value={a}>{a}</option>{/each}
		</select>
		<select class="field" bind:value={action} aria-label="Action">
			<option value="">Any action</option>
			{#each actions as a (a)}<option value={a}>{a}</option>{/each}
		</select>
		<SegmentedFilter
			bind:value={outcome}
			options={[
				{ value: 'any', label: 'All' },
				{ value: 'allowed', label: 'Allowed' },
				{ value: 'denied', label: 'Denied' }
			]}
		/>
		<label class="check">
			<input type="checkbox" class="sb-check" bind:checked={evidenceOnly} />
			Evidence reads only
		</label>
		<span class="total">{rows.length} entries</span>
	</div>

	<div class="sb-list-wrap">
		<table class="sb-list static">
			<thead>
				<tr>
					<th>When</th>
					<th>Actor</th>
					<th>Action</th>
					<th>Scope</th>
					<th>Outcome</th>
					<th>Granted by</th>
					<th>Detail</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as e (e.id)}
					<tr>
						<td><RelativeTime value={formatAgo(e.at, app.now)} exact={formatStamp(e.at)} /></td>
						<td>
							{e.actor.name}
							<div class="cell-desc">{e.ip}</div>
						</td>
						<td>
							<code>{e.action}</code>
							{#if e.evidenceRead}<span class="evidence" title="Read of evidence (sample or failing rows)"><EyeIcon size={12} /> evidence</span>{/if}
						</td>
						<td class="muted">
							{formatAssignmentScope(e.scope, locations)}
							{#if e.scope.subject}<div class="cell-desc"><code>{e.scope.subject}</code></div>{/if}
						</td>
						<td><StatusLabel tone={e.outcome === 'denied' ? 'var(--sb-error)' : 'var(--sb-success)'} label={e.outcome === 'denied' ? 'Denied' : 'Allowed'} /></td>
						<td class="muted">{e.grantingRole ?? '—'}</td>
						<td class="detail">
							{e.summary}
							<div class="cell-desc" title="Request {e.requestId}">
								{#if e.before !== null || e.after !== null}<code>{e.before ?? '∅'} → {e.after ?? '∅'}</code> ·{/if}
								<code>{e.requestId}</code>
							</div>
						</td>
					</tr>
				{:else}
					<LoadRow colspan={7} resource={entries} empty="No audit entries match the filters." />
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	:global(.sb-list.static tbody tr) {
		cursor: default;
	}
	.toolbar {
		display: flex;
		height: 50px;
		flex: 0 0 50px;
		align-items: center;
		gap: 8px;
		padding: 0 20px;
		border-bottom: 1px solid var(--border);
	}
	.field {
		height: 30px;
		padding: 0 8px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--background);
		color: var(--foreground);
		font-size: 12.5px;
	}
	.check {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		margin-left: 6px;
		color: var(--muted-foreground);
		font-size: 12.5px;
	}
	.total {
		margin-left: auto;
		font-size: 12px;
		font-weight: 500;
	}
	.evidence {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		margin-left: 6px;
		color: var(--sb-warning);
		font-size: 11.5px;
	}
	.detail {
		max-width: 420px;
	}
</style>
