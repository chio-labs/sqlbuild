<script lang="ts">
	import { Database, HardDrive, KeyRound, Bell, type Icon as IconType } from '@lucide/svelte';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import { goto } from '$app/navigation';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';

	// Providers = SQLBuild's configured connections/integrations (adapters, loaders'
	// external systems, etc.) that models/loaders depend on at execution time.
	type Kind = 'adapter' | 'storage' | 'secret' | 'notifier';
	type ConnStatus = 'connected' | 'error' | 'unused';
	type Provider = {
		id: string;
		name: string;
		kind: Kind;
		type: string; // duckdb / snowflake / s3 / slack ...
		status: ConnStatus;
		uses: number; // how many nodes use it
		summary: string;
	};

	const providers: Provider[] = [
		{ id: 'duckdb_dev', name: 'duckdb · dev', kind: 'adapter', type: 'duckdb', status: 'connected', uses: 16, summary: 'Local DuckDB target for dev builds and replay.' },
		{ id: 'snowflake_prod', name: 'snowflake · prod', kind: 'adapter', type: 'snowflake', status: 'connected', uses: 16, summary: 'Production Snowflake warehouse (WAFFLE_SHOP.PROD).' },
		{ id: 'orders_api', name: 'orders_api', kind: 'storage', type: 'rest', status: 'connected', uses: 1, summary: 'Source loader connection for raw__orders ingestion.' },
		{ id: 's3_archive', name: 's3_archive', kind: 'storage', type: 's3', status: 'connected', uses: 2, summary: 'S3 bucket for CSV exports and backups.' },
		{ id: 'slack_alerts', name: 'slack_alerts', kind: 'notifier', type: 'slack', status: 'connected', uses: 1, summary: 'Posts run-failure alerts to #data-alerts.' },
		{ id: 'bigquery_eu', name: 'bigquery · eu', kind: 'adapter', type: 'bigquery', status: 'error', uses: 0, summary: 'Service account credentials expired.' }
	];

	const statusColor: Record<ConnStatus, string> = {
		connected: 'var(--sb-success)',
		error: 'var(--sb-error)',
		unused: 'var(--sb-text-faint)'
	};
	const statusLabel: Record<ConnStatus, string> = { connected: 'Connected', error: 'Error', unused: 'Unused' };
	const kindIcon: Record<Kind, typeof IconType> = { adapter: Database, storage: HardDrive, secret: KeyRound, notifier: Bell };

	let query = $state('');
	const filtered = $derived(
		providers.filter((p) => {
			if (!query.trim()) return true;
			const q = query.toLowerCase();
			return p.name.toLowerCase().includes(q) || p.type.toLowerCase().includes(q) || p.kind.includes(q);
		})
	);
</script>

<AppTopbar title="Providers">
	<Button variant="outline" size="sm">↻ Test all</Button>
	<Button size="sm">+ Add provider</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder="Search providers"
	total="{filtered.length} of {providers.length} providers"
	counts={[{ tone: 'var(--sb-error)', count: providers.filter((p) => p.status === 'error').length, label: 'error' }]}
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
				<th>Provider</th>
				<th>Kind</th>
				<th>Type</th>
				<th>Status</th>
				<th class="num">Used by</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as p (p.id)}
				{@const Glyph = kindIcon[p.kind]}
				<tr onclick={() => goto(`/providers/${p.id}`)}>
					<td>
						<div class="cell-name">
							<Glyph size={15} strokeWidth={1.75} />
							<div class="min-w-0">
								<a href="/providers/{p.id}" onclick={(e) => e.stopPropagation()}>{p.name}</a>
								<div class="cell-desc">{p.summary}</div>
							</div>
						</div>
					</td>
					<td class="muted capitalize">{p.kind}</td>
					<td><code>{p.type}</code></td>
					<td><StatusLabel tone={statusColor[p.status]} label={statusLabel[p.status]} /></td>
					<td class="num muted">{p.uses} {p.uses === 1 ? 'node' : 'nodes'}</td>
				</tr>
			{:else}
				<tr><td colspan="5" class="empty">No providers match the filter.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
