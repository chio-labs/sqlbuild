<script lang="ts">
	import { Database, Plug, Bell, type Icon as IconType } from '@lucide/svelte';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import { goto } from '$app/navigation';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import type { ConnectionKind, ConnectionStatus } from '$lib/api';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';

	const connections = createResource((client, scope) => client.listConnections(scope));

	const statusColor: Record<ConnectionStatus, string> = {
		ok: 'var(--sb-success)',
		error: 'var(--sb-error)',
		untested: 'var(--sb-text-faint)'
	};
	const statusLabel: Record<ConnectionStatus, string> = { ok: 'Connected', error: 'Error', untested: 'Not tested' };
	const kindIcon: Record<ConnectionKind, typeof IconType> = { warehouse: Database, provider: Plug, channel: Bell };

	let query = $state('');
	const all = $derived(connections.data ?? []);
	const filtered = $derived(
		all.filter((c) => {
			if (!query.trim()) return true;
			const q = query.toLowerCase();
			return c.name.toLowerCase().includes(q) || c.type.toLowerCase().includes(q) || c.kind.includes(q);
		})
	);
</script>

<AppTopbar title="Connections">
	<Button variant="outline" size="sm" disabled={!app.can('connection.test')} title={app.can('connection.test') ? undefined : 'Requires connection.test'}>↻ Test all</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder="Search connections"
	total="{filtered.length} of {all.length} connections"
	counts={[{ tone: 'var(--sb-error)', count: all.filter((c) => c.status === 'error').length, label: 'error' }]}
>
	{#snippet filters()}
		<FilterButton label="Kind" />
		<FilterButton label="Status" />
	{/snippet}
</ListToolbar>

<div class="sb-list-wrap">
	<table class="sb-list">
		<thead>
			<tr>
				<th>Connection</th>
				<th>Kind</th>
				<th>Type</th>
				<th>Status</th>
				<th class="num">Used by</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as c (c.id)}
				{@const Glyph = kindIcon[c.kind]}
				<tr onclick={() => goto(`/connections/${c.id}`)}>
					<td>
						<div class="cell-name">
							<Glyph size={15} strokeWidth={1.75} />
							<div class="min-w-0">
								<a href="/connections/{c.id}" onclick={(e) => e.stopPropagation()}>{c.name}</a>
								<div class="cell-desc">{c.summary}</div>
							</div>
						</div>
					</td>
					<td class="muted capitalize">{c.kind}</td>
					<td><code>{c.type}</code></td>
					<td><StatusLabel tone={statusColor[c.status]} label={statusLabel[c.status]} /></td>
					<td class="num muted">{c.usedBy} {c.usedBy === 1 ? 'node' : 'nodes'}</td>
				</tr>
			{:else}
				<LoadRow colspan={5} resource={connections} empty={all.length ? 'No connections match the filter.' : 'No connections configured for this target.'} />
			{/each}
		</tbody>
	</table>
</div>
