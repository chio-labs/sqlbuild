<script lang="ts">
	import { goto } from '$app/navigation';
	import {
		Database,
		Download,
		Sprout,
		Table2,
		Workflow,
		Box,
		ShieldCheck,
		FunctionSquare,
		type Icon as IconType
	} from '@lucide/svelte';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import SegmentedFilter from '$lib/components/list/segmented-filter.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';

	type Status = 'fresh' | 'stale' | 'warn' | 'fail' | 'source';
	// node type = first-class SQLBuild DAG node kind
	type NodeType = 'model' | 'source' | 'loader' | 'seed' | 'task' | 'asset' | 'check' | 'udf';
	type Model = {
		name: string;
		desc: string;
		kind: string; // display sub-kind (e.g. 'view', 'incremental · merge', 'python')
		nodeType: NodeType;
		tags: string[];
		status: Status;
		built: string;
		checks: string;
		checksStatus: 'ok' | 'warn' | 'fail' | 'none';
	};

	const models: Model[] = [
		{ name: 'raw__customers', desc: 'External customer source table', kind: 'source', nodeType: 'source', tags: [], status: 'source', built: '8m ago', checks: '—', checksStatus: 'none' },
		{ name: 'raw__orders', desc: 'External orders source (merge)', kind: 'source · merge', nodeType: 'source', tags: [], status: 'source', built: '8m ago', checks: '—', checksStatus: 'none' },
		{ name: 'raw__payments', desc: 'External payments source', kind: 'source', nodeType: 'source', tags: [], status: 'source', built: '8m ago', checks: '—', checksStatus: 'none' },
		{ name: 'load_raw_orders', desc: 'Python loader: incremental orders from API', kind: 'loader · delete_insert', nodeType: 'loader', tags: ['ingest'], status: 'fresh', built: '8m ago', checks: '—', checksStatus: 'none' },
		{ name: 'load__waffle_cust', desc: 'Python loader: customer extract', kind: 'loader · table', nodeType: 'loader', tags: ['ingest'], status: 'fresh', built: '8m ago', checks: '—', checksStatus: 'none' },
		{ name: 'waffle_types', desc: 'Seed of waffle product types', kind: 'seed', nodeType: 'seed', tags: [], status: 'fresh', built: '8m ago', checks: '—', checksStatus: 'none' },
		{ name: 'grant_target', desc: 'Python UDF: grant SELECT on target', kind: 'udf · python', nodeType: 'udf', tags: [], status: 'fresh', built: '8m ago', checks: '—', checksStatus: 'none' },
		{ name: 'fn_customer_ltv', desc: 'SQL table function: customer lifetime value', kind: 'udf · table', nodeType: 'udf', tags: [], status: 'fresh', built: '6m ago', checks: '—', checksStatus: 'none' },
		{ name: 'stg_customers', desc: 'Cleaned customers from raw', kind: 'view', nodeType: 'model', tags: [], status: 'fresh', built: '6m ago', checks: '3 / 3', checksStatus: 'ok' },
		{ name: 'stg_orders', desc: 'Cleaned orders from raw', kind: 'view', nodeType: 'model', tags: [], status: 'fresh', built: '6m ago', checks: '4 / 4', checksStatus: 'ok' },
		{ name: 'stg_payments', desc: 'Cleaned payments from raw', kind: 'view', nodeType: 'model', tags: [], status: 'warn', built: '6m ago', checks: '0 / 1', checksStatus: 'warn' },
		{ name: 'fact_orders', desc: 'One row per order with payment + customer', kind: 'table', nodeType: 'model', tags: ['finance', 'core'], status: 'fresh', built: '4m ago', checks: '1 / 1', checksStatus: 'ok' },
		{ name: 'daily_revenue', desc: 'Daily revenue rollup by completed orders', kind: 'table', nodeType: 'model', tags: ['finance', 'revenue'], status: 'fresh', built: '6m ago', checks: '1 / 1', checksStatus: 'ok' },
		{ name: 'dim_customers', desc: 'Customer dimension with first/last order', kind: 'table', nodeType: 'model', tags: ['core'], status: 'fresh', built: '4m ago', checks: '2 / 2', checksStatus: 'ok' },
		{ name: 'customer_status', desc: 'Upserted customer status snapshot', kind: 'incremental · merge', nodeType: 'model', tags: [], status: 'stale', built: '2d ago', checks: '2 / 2', checksStatus: 'ok' },
		{ name: 'order_status_idx', desc: 'Order status index', kind: 'incremental · delete_insert', nodeType: 'model', tags: [], status: 'fresh', built: '5m ago', checks: '—', checksStatus: 'none' },
		{ name: 'hourly_order_act', desc: 'Hourly order activity (microbatch)', kind: 'incremental · delete_insert', nodeType: 'model', tags: ['activity'], status: 'fresh', built: '5m ago', checks: '—', checksStatus: 'none' },
		{ name: 'daily_activity', desc: 'Daily activity rollup (microbatch)', kind: 'incremental · delete_insert', nodeType: 'model', tags: ['activity'], status: 'stale', built: '1d ago', checks: '2 / 2', checksStatus: 'ok' },
		{ name: 'hourly_activity_ctx', desc: 'Hourly activity with daily context', kind: 'incremental · delete_insert', nodeType: 'model', tags: ['activity'], status: 'fail', built: 'failed', checks: '0 / 1', checksStatus: 'fail' },
		{ name: 'export_revenue_csv', desc: 'Python task: export revenue to S3', kind: 'task · python', nodeType: 'task', tags: ['export'], status: 'fresh', built: '3m ago', checks: '—', checksStatus: 'none' },
		{ name: 'revenue_dashboard', desc: 'Python asset: refresh BI dashboard', kind: 'asset · python', nodeType: 'asset', tags: ['bi'], status: 'fresh', built: '3m ago', checks: '1 / 1', checksStatus: 'ok' },
		{ name: 'check_revenue_reconciles', desc: 'Standalone check: revenue reconciliation', kind: 'check', nodeType: 'check', tags: ['finance'], status: 'fresh', built: '3m ago', checks: '1 / 1', checksStatus: 'ok' }
	];

	const statusColor: Record<Status, string> = {
		fresh: 'var(--sb-success)',
		stale: 'var(--sb-stale)',
		warn: 'var(--sb-warning)',
		fail: 'var(--sb-error)',
		source: 'var(--sb-text-faint)'
	};
	const statusLabel: Record<Status, string> = {
		fresh: 'Fresh',
		stale: 'Stale',
		warn: 'Warning',
		fail: 'Failed',
		source: 'External'
	};
	const typeIcon: Record<NodeType, typeof IconType> = {
		source: Database,
		loader: Download,
		seed: Sprout,
		model: Table2,
		task: Workflow,
		asset: Box,
		check: ShieldCheck,
		udf: FunctionSquare
	};
	const checkColor: Record<string, string> = {
		ok: 'var(--sb-success)',
		warn: 'var(--sb-warning)',
		fail: 'var(--sb-error)',
		none: 'var(--sb-text-faint)'
	};
	let query = $state('');
	// filter by node type (first-class SQLBuild DAG node kinds), not dbt-style folder layers
	let typeFilter = $state<'all' | NodeType>('all');
	const nodeTypes: ('all' | NodeType)[] = ['all', 'source', 'seed', 'loader', 'model', 'task', 'asset', 'check', 'udf'];
	const typeLabel: Record<'all' | NodeType, string> = {
		all: 'All',
		model: 'Models',
		source: 'Sources',
		seed: 'Seeds',
		loader: 'Loaders',
		task: 'Tasks',
		asset: 'Assets',
		check: 'Checks',
		udf: 'UDFs'
	};

	const filtered = $derived(
		models.filter((m) => {
			if (typeFilter !== 'all' && m.nodeType !== typeFilter) return false;
			if (query.trim()) {
				const q = query.toLowerCase();
				return (
					m.name.toLowerCase().includes(q) ||
					m.desc.toLowerCase().includes(q) ||
					m.kind.toLowerCase().includes(q) ||
					m.tags.some((t) => t.toLowerCase().includes(q))
				);
			}
			return true;
		})
	);

	const counts = $derived({
		total: models.length,
		fresh: models.filter((m) => m.status === 'fresh').length,
		stale: models.filter((m) => m.status === 'stale').length,
		warn: models.filter((m) => m.status === 'warn').length,
		fail: models.filter((m) => m.status === 'fail').length
	});
</script>

<AppTopbar title="Catalog">
	<Button variant="outline" size="sm">↻ Refresh</Button>
	<Button size="sm">▷ Execute</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder="Search catalog"
	total="{filtered.length} of {counts.total} nodes"
	counts={[
		{ tone: 'var(--sb-success)', count: counts.fresh, label: 'fresh' },
		{ tone: 'var(--sb-stale)', count: counts.stale, label: 'stale' },
		{ tone: 'var(--sb-warning)', count: counts.warn, label: 'warning' },
		{ tone: 'var(--sb-error)', count: counts.fail, label: 'failed' }
	]}
>
	{#snippet filters()}
		<SegmentedFilter bind:value={typeFilter} options={nodeTypes.map((t) => ({ value: t, label: typeLabel[t] }))} />
		<FilterButton label="Tags" />
	{/snippet}
</ListToolbar>

<div class="sb-list-wrap">
	<table class="sb-list">
		<thead>
			<tr>
				<th>Name</th>
				<th>Kind</th>
				<th>Tags</th>
				<th>Status</th>
				<th class="num">Checks</th>
				<th>Last built</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as m (m.name)}
				{@const Glyph = typeIcon[m.nodeType]}
				<tr onclick={() => goto(`/catalog/${m.name}`)}>
					<td>
						<div class="cell-name">
							<Glyph size={15} strokeWidth={1.75} />
							<div class="min-w-0">
								<a href="/catalog/{m.name}" onclick={(e) => e.stopPropagation()}>{m.name}</a>
								<div class="cell-desc">{m.desc}</div>
							</div>
						</div>
					</td>
					<td class="muted">{m.kind}</td>
					<td>
						{#if m.tags.length}
							<div class="flex flex-wrap gap-1">{#each m.tags as t (t)}<span class="sb-tag">{t}</span>{/each}</div>
						{:else}<span class="muted">—</span>{/if}
					</td>
					<td><StatusLabel tone={statusColor[m.status]} label={statusLabel[m.status]} muted={m.status === 'source'} /></td>
					<td class="num" style:color={m.checksStatus === 'none' ? 'var(--muted-foreground)' : checkColor[m.checksStatus]}>{m.checks}</td>
					<td><RelativeTime value={m.built} /></td>
				</tr>
			{:else}
				<tr><td colspan="6" class="empty">No nodes match the filter.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
