<script lang="ts">
	import { page } from '$app/state';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import ConfigForm, { type Field } from '$lib/config/config-form.svelte';

	const id = $derived(page.params.id ?? 'snowflake_prod');

	type Tab = 'config' | 'uses';
	let tab = $state<Tab>('config');

	// mock provider definition (snowflake adapter for this mock)
	const def = {
		name: 'snowflake · prod',
		type: 'snowflake',
		kind: 'adapter',
		status: 'connected' as 'connected' | 'error',
		desc: 'Production Snowflake warehouse used as the target for promoted models. Connection is validated before each build; failed audits block promotion so the target table is never left in a bad state.'
	};

	// schema = the Pydantic provider-settings shape (Hub renders typed controls from this)
	const schema: Field[] = [
		{ key: 'account', label: 'account', type: 'string', required: true, description: 'Snowflake account identifier' },
		{ key: 'database', label: 'database', type: 'string', required: true, description: 'Target database' },
		{ key: 'schema', label: 'schema', type: 'string', default: 'PROD', description: 'Default schema for models' },
		{ key: 'warehouse', label: 'warehouse', type: 'string', required: true, description: 'Compute warehouse' },
		{ key: 'role', label: 'role', type: 'string', default: 'TRANSFORMER', description: 'Session role' },
		{ key: 'threads', label: 'threads', type: 'int', default: 8, min: 1, max: 32, description: 'Concurrent build threads' },
		{ key: 'auth_method', label: 'auth_method', type: 'enum', enum: ['password', 'keypair', 'sso'], default: 'password', description: 'Authentication method' },
		{ key: 'password', label: 'password', type: 'secret', required: true, secretSource: 'env: SNOWFLAKE_PASSWORD', description: 'Auth secret' }
	];
	// durable values configured for this provider (read-only here — lives in the
	// version-controlled project config; per-run edits happen in the Run panel)
	let values = $state<Record<string, unknown>>({
		account: 'xy12345.eu-west-1',
		database: 'WAFFLE_SHOP',
		warehouse: 'TRANSFORMING_WH'
		// schema/role/threads/auth_method left as schema defaults
	});

	const usedByModels = ['stg_customers', 'stg_orders', 'stg_payments', 'fact_orders', 'dim_customers', 'daily_revenue'];
	const usedByJobs = ['nightly_build', 'marts_only'];
</script>

<AppTopbar title="Providers">
	<Button variant="outline" size="sm">↻ Test connection</Button>
	<Button variant="outline" size="sm">Edit</Button>
</AppTopbar>

<div class="flex min-h-0 flex-1 flex-col">
	<!-- header -->
	<div class="flex items-center gap-3 border-b border-border px-6 py-3.5">
		<a href="/providers" class="text-muted-foreground hover:text-foreground text-[13px]">← Providers</a>
		<span class="font-display text-[17px] font-semibold">{def.name}</span>
		<span class="text-muted-foreground text-[12px]">{def.kind} · {def.type}</span>
		<span class="ml-auto inline-flex items-center gap-1.5 text-[11.5px]" style:color={def.status === 'connected' ? 'var(--sb-secondary)' : 'var(--sb-error)'}>
			<span class="h-1.5 w-1.5 rounded-[2px]" style:background={def.status === 'connected' ? 'var(--sb-secondary)' : 'var(--sb-error)'}></span>{def.status}
		</span>
	</div>

	<div class="flex min-h-0 flex-1">
		<!-- main -->
		<div class="min-h-0 flex-1 overflow-auto">
			<div class="flex items-center gap-1 border-b border-border px-4">
				{#each [['config', 'Configuration'], ['uses', `Used by · ${usedByModels.length + usedByJobs.length}`]] as [t, lbl] (t)}
					<button
						class="border-b-2 px-3 py-2.5 text-[12.5px] {tab === t ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground'}"
						onclick={() => (tab = t as Tab)}
					>{lbl}</button>
				{/each}
			</div>

			{#if tab === 'config'}
				<div class="flex max-w-[680px] flex-col p-6">
					<div class="text-[var(--sb-text-faint)] mb-4 flex items-center gap-2 rounded-[2px] border border-[var(--border-subtle)] bg-[var(--sb-surface-low)] px-3 py-2 text-[11.5px]">
						<span>🔒</span>
						<span>Read-only — defined in your project config. Override per run from the lineage Run panel.</span>
					</div>
					<ConfigForm {schema} bind:values readOnly />
				</div>
			{:else}
				<div class="flex flex-col gap-6 p-6">
					<div>
						<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Models · {usedByModels.length}</div>
						<div class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-1.5">
							{#each usedByModels as m (m)}
								<a href="/catalog/{m}" class="bg-secondary hover:bg-[var(--sb-hover)] flex items-center gap-2 rounded-[2px] border border-border px-2.5 py-1.5 text-[12px]">{m}</a>
							{/each}
						</div>
					</div>
					<div>
						<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Jobs · {usedByJobs.length}</div>
						<div class="flex flex-wrap gap-1.5">
							{#each usedByJobs as j (j)}
								<a href="/jobs/{j}" class="bg-secondary hover:bg-[var(--sb-hover)] rounded-[2px] border border-border px-2.5 py-1.5 text-[12px]">{j}</a>
							{/each}
						</div>
					</div>
				</div>
			{/if}
		</div>

		<!-- right: description rail -->
		<div class="w-[300px] shrink-0 overflow-auto border-l border-border p-5">
			<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Provider</div>
			<div class="flex flex-col gap-2 text-[12.5px]">
				{#each [['Kind', def.kind], ['Type', def.type], ['Status', def.status]] as [k, v] (k)}
					<div class="flex items-baseline justify-between gap-3">
						<span class="text-muted-foreground">{k}</span>
						<span class="text-right text-[11.5px]">{v}</span>
					</div>
				{/each}
			</div>
			<div class="mt-5">
				<div class="text-[var(--sb-text-faint)] mb-1.5 text-[12px] font-medium">Description</div>
				<p class="text-muted-foreground text-[12.5px] leading-relaxed">{def.desc}</p>
			</div>
		</div>
	</div>
</div>
