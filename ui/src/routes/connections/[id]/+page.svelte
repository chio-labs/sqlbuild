<script lang="ts">
	import { page } from '$app/state';
	import LockIcon from '@lucide/svelte/icons/lock';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import ConfigForm from '$lib/config/config-form.svelte';
	import ConnectionTest from '$lib/components/platform/connection-test.svelte';
	import KeyValues from '$lib/components/platform/key-values.svelte';
	import PageTabs from '$lib/components/platform/page-tabs.svelte';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';

	const name = $derived(page.params.id ?? '');
	const connections = createResource((client, scope) => client.connections(scope));

	const warehouse = $derived(connections.data?.warehouse.find((c) => c.name === name) ?? null);
	const provider = $derived(connections.data?.providers.find((p) => p.name === name) ?? null);
	const found = $derived(warehouse ?? provider);

	type Tab = 'settings' | 'uses';
	let tab = $state<Tab>('settings');
	const usedCount = $derived(provider ? provider.usedBy.nodes.length + provider.usedBy.jobs.length : 0);
</script>

<AppTopbar title="Connections">
	<Button variant="outline" size="sm" onclick={() => connections.refresh()}>↻ Refresh</Button>
</AppTopbar>

<div class="flex min-h-0 flex-1 flex-col">
	<div class="flex items-center gap-3 border-b border-border px-6 py-3.5">
		<a href="/connections" class="text-muted-foreground hover:text-foreground text-[13px]">← Connections</a>
		<span class="font-display text-[17px] font-semibold">{name}</span>
		{#if warehouse}
			<span class="text-muted-foreground text-[12px]">Warehouse · {warehouse.adapter} · target {warehouse.target}</span>
		{:else if provider}
			<span class="text-muted-foreground text-[12px]">Provider · {provider.type}</span>
		{/if}
	</div>

	{#if connections.error}
		<div class="text-[var(--sb-error)] px-6 py-4 text-[13px]">Couldn't load connections: {connections.error}</div>
	{:else if connections.data && !found}
		<div class="text-muted-foreground px-6 py-4 text-[13px]">No connection named <code>{name}</code> for target {app.targetName}.</div>
	{:else if found}
		<div class="flex min-h-0 flex-1">
			<div class="min-h-0 flex-1 overflow-auto">
				{#if provider}
					<PageTabs
						bind:value={tab}
						tabs={[
							{ value: 'settings', label: 'Settings' },
							{ value: 'uses', label: 'Used by', count: usedCount }
						]}
					/>
				{/if}

				{#if tab === 'settings' || !provider}
					<div class="flex max-w-[680px] flex-col p-6">
						{#if warehouse}
							<div class="mb-5">
								<ConnectionTest scope={{ locationId: app.locationId, target: app.targetName }} connection={warehouse.name} last={warehouse.lastTest} />
							</div>
						{/if}
						<div class="text-[var(--sb-text-faint)] mb-4 flex items-center gap-2 rounded-[2px] border border-[var(--border-subtle)] bg-[var(--sb-surface-low)] px-3 py-2 text-[11.5px]">
							<LockIcon size={12} />
							<span>Read-only. Defined in <code>{found.sourceFile}</code>; secrets show only where they come from.</span>
						</div>
						<ConfigForm schema={found.settings} values={found.values} readOnly />
					</div>
				{:else}
					<div class="flex flex-col gap-6 p-6">
						<div>
							<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Nodes · {provider.usedBy.nodes.length}</div>
							<div class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-1.5">
								{#each provider.usedBy.nodes as m (m)}
									<a href="/catalog/{m}" class="bg-secondary hover:bg-[var(--sb-hover)] flex items-center gap-2 rounded-[2px] border border-border px-2.5 py-1.5 text-[12px]">{m}</a>
								{/each}
							</div>
						</div>
						<div>
							<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Jobs · {provider.usedBy.jobs.length}</div>
							<div class="flex flex-wrap gap-1.5">
								{#each provider.usedBy.jobs as j (j)}
									<a href="/jobs/{j}" class="bg-secondary hover:bg-[var(--sb-hover)] rounded-[2px] border border-border px-2.5 py-1.5 text-[12px]">{j}</a>
								{/each}
							</div>
						</div>
					</div>
				{/if}
			</div>

			<aside class="w-[300px] shrink-0 overflow-auto border-l border-border p-5">
				<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">{warehouse ? 'Warehouse connection' : 'Provider'}</div>
				{#if warehouse}
					<KeyValues
						rows={[
							{ label: 'Adapter', value: warehouse.adapter },
							{ label: 'Target', value: warehouse.target },
							{ label: 'Used for', value: warehouse.purpose === 'catalog' ? 'Warehouse sync (catalog_connection)' : 'Builds and warehouse sync' },
							{ label: 'Source', value: warehouse.sourceFile, mono: true }
						]}
					/>
				{:else if provider}
					<KeyValues
						rows={[
							{ label: 'Type', value: provider.type },
							{ label: 'Source', value: provider.sourceFile, mono: true }
						]}
					/>
					<p class="text-muted-foreground mt-5 text-[12.5px] leading-relaxed">{provider.description}</p>
				{/if}
			</aside>
		</div>
	{:else}
		<div class="text-muted-foreground px-6 py-4 text-[13px]">Loading…</div>
	{/if}
</div>
