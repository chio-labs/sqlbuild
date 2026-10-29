<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import { highlightSqlbuild } from '$lib/sql/highlight';
	import { mockModelSql, modelVersions, MODEL_DRIFT } from '$lib/mock/model-sql';
	import GitCompareIcon from '@lucide/svelte/icons/git-compare';
	import CodePreview from '$lib/components/code/code-preview.svelte';
	import SqlViewer from '$lib/components/code/sql-viewer.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import { Database, Download, Sprout, Table2, Workflow, Box, ShieldCheck, FunctionSquare, type Icon as IconType } from '@lucide/svelte';
	import ScopedLineage from '$lib/lineage/scoped-lineage.svelte';
	import ColumnLineage from '$lib/lineage/column-lineage.svelte';

	// column-level lineage mock (models + column->column edges)
	type Lens = 'raw' | 'passthrough' | 'rename' | 'transform';
	const colModels = [
		{ id: 'raw__orders', name: 'raw__orders', kind: 'source', status: 'src' as const, columns: [{ name: 'id', type: 'BIGINT' }, { name: 'cust_id', type: 'BIGINT' }, { name: 'status', type: 'TEXT' }] },
		{ id: 'raw__payments', name: 'raw__payments', kind: 'source', status: 'src' as const, columns: [{ name: 'order_id', type: 'BIGINT' }, { name: 'amount_cents', type: 'INT' }, { name: 'method', type: 'TEXT' }] },
		{ id: 'stg_orders', name: 'stg_orders', kind: 'view', status: 'ok' as const, columns: [{ name: 'order_id', type: 'BIGINT' }, { name: 'customer_id', type: 'BIGINT' }, { name: 'order_status', type: 'VARCHAR' }] },
		{ id: 'stg_payments', name: 'stg_payments', kind: 'view', status: 'stale' as const, columns: [{ name: 'order_id', type: 'BIGINT' }, { name: 'amount_cents', type: 'INT' }, { name: 'payment_method', type: 'VARCHAR' }] },
		{ id: 'fact_orders', name: 'fact_orders', kind: 'table', status: 'stale' as const, columns: [{ name: 'order_id', type: 'BIGINT' }, { name: 'customer_id', type: 'BIGINT' }, { name: 'order_status', type: 'VARCHAR' }, { name: 'total_cents', type: 'INT' }, { name: 'payment_method', type: 'VARCHAR' }] },
		{ id: 'daily_revenue', name: 'daily_revenue', kind: 'table', status: 'ok' as const, columns: [{ name: 'revenue_date', type: 'DATE' }, { name: 'total_revenue_cents', type: 'BIGINT' }] }
	];
	const colEdges: [string, string, Lens][] = [
		['raw__orders.id', 'stg_orders.order_id', 'rename'],
		['raw__orders.cust_id', 'stg_orders.customer_id', 'rename'],
		['raw__orders.status', 'stg_orders.order_status', 'rename'],
		['raw__payments.order_id', 'stg_payments.order_id', 'passthrough'],
		['raw__payments.amount_cents', 'stg_payments.amount_cents', 'passthrough'],
		['raw__payments.method', 'stg_payments.payment_method', 'rename'],
		['stg_orders.order_id', 'fact_orders.order_id', 'passthrough'],
		['stg_orders.customer_id', 'fact_orders.customer_id', 'passthrough'],
		['stg_orders.order_status', 'fact_orders.order_status', 'passthrough'],
		['stg_payments.amount_cents', 'fact_orders.total_cents', 'transform'],
		['stg_payments.payment_method', 'fact_orders.payment_method', 'passthrough'],
		['fact_orders.total_cents', 'daily_revenue.total_revenue_cents', 'transform']
	];

	const name = $derived(page.params.name ?? 'fact_orders');

	// project graph (mock) used by the scoped lineage tab
	const graphNodes: { id: string; name: string; kind: string; status: 'ok' | 'fail' | 'warn' | 'stale' | 'src'; icon?: string }[] = [
		{ id: 'raw__customers', name: 'raw__customers', kind: 'source', status: 'src', icon: 'source' },
		{ id: 'raw__orders', name: 'raw__orders', kind: 'source · merge', status: 'src', icon: 'loader' },
		{ id: 'raw__payments', name: 'raw__payments', kind: 'source', status: 'src', icon: 'source' },
		{ id: 'stg_customers', name: 'stg_customers', kind: 'view', status: 'ok', icon: 'view' },
		{ id: 'stg_orders', name: 'stg_orders', kind: 'view', status: 'ok', icon: 'view' },
		{ id: 'stg_payments', name: 'stg_payments', kind: 'view', status: 'stale', icon: 'view' },
		{ id: 'fact_orders', name: 'fact_orders', kind: 'table', status: 'stale', icon: 'table' },
		{ id: 'dim_customers', name: 'dim_customers', kind: 'table', status: 'stale', icon: 'table' },
		{ id: 'customer_status', name: 'customer_status', kind: 'incremental · merge', status: 'stale', icon: 'merge' },
		{ id: 'order_status_idx', name: 'order_status_idx', kind: 'incremental · delete_insert', status: 'stale', icon: 'delete_insert' },
		{ id: 'hourly_order_act', name: 'hourly_order_act', kind: 'incremental · delete_insert', status: 'stale', icon: 'microbatch' },
		{ id: 'daily_activity', name: 'daily_activity', kind: 'incremental · delete_insert', status: 'stale', icon: 'microbatch' }
	];
	const graphEdges: [string, string][] = [
		['raw__customers', 'stg_customers'],
		['raw__orders', 'stg_orders'],
		['raw__payments', 'stg_payments'],
		['stg_customers', 'fact_orders'],
		['stg_orders', 'fact_orders'],
		['stg_payments', 'fact_orders'],
		['fact_orders', 'dim_customers'],
		['fact_orders', 'customer_status'],
		['fact_orders', 'order_status_idx'],
		['fact_orders', 'hourly_order_act'],
		['fact_orders', 'daily_activity']
	];

	// infer node type from the name (mock); real impl would come from the API
	type NodeType = 'model' | 'source' | 'loader' | 'seed' | 'task' | 'asset' | 'check' | 'udf';
	const nodeType = $derived<NodeType>(
		name.startsWith('raw__')
			? 'source'
			: name.startsWith('load')
				? 'loader'
				: name.startsWith('export_') || name.startsWith('task_')
					? 'task'
					: name.includes('dashboard') || name.startsWith('asset_')
						? 'asset'
						: name.startsWith('check_')
							? 'check'
							: name.startsWith('fn_') || name.startsWith('grant_')
								? 'udf'
								: name === 'waffle_types'
									? 'seed'
									: 'model'
	);
	const isModel = $derived(nodeType === 'model');
	const isPython = $derived(nodeType === 'loader' || nodeType === 'task' || nodeType === 'asset');
	const hasColumns = $derived(nodeType === 'model' || nodeType === 'source' || nodeType === 'asset');
	const hasSql = $derived(nodeType === 'model');

	// adaptive tab set per node type
	type Tab = 'overview' | 'columns' | 'lineage' | 'collineage' | 'sql' | 'code' | 'definition' | 'runs';
	const tabs = $derived.by<[Tab, string][]>(() => {
		// SQL/Code live inline on Overview (no separate tab needed)
		const t: [Tab, string][] = [['overview', 'Overview']];
		if (hasColumns) t.push(['columns', 'Columns']);
		if (hasSql) t.push(['sql', 'SQL']);
		if (isPython || nodeType === 'udf') t.push(['code', 'Code']);
		if (nodeType === 'check') t.push(['definition', 'Definition']);
		t.push(['lineage', 'Lineage']);
		if (isModel) t.push(['collineage', 'Column lineage']);
		if (nodeType !== 'udf') t.push(['runs', 'Runs']);
		return t;
	});
	const ALL_TABS: Tab[] = ['overview', 'columns', 'sql', 'code', 'definition', 'lineage', 'collineage', 'runs'];
	// the URL is the single source of truth for the tab, so back/forward and reloads restore it
	const tab = $derived<Tab>(
		ALL_TABS.includes(page.url.searchParams.get('tab') as Tab) ? (page.url.searchParams.get('tab') as Tab) : 'overview'
	);

	const headerStatus = $derived.by(() => {
		const st = graphNodes.find((n) => n.name === name)?.status ?? 'ok';
		return (
			{
				ok: { tone: 'var(--sb-success)', label: 'Fresh' },
				stale: { tone: 'var(--sb-stale)', label: 'Stale' },
				warn: { tone: 'var(--sb-warning)', label: 'Warning' },
				fail: { tone: 'var(--sb-error)', label: 'Failed' },
				src: { tone: 'var(--sb-text-faint)', label: 'External' }
			} as const
		)[st];
	});

	function setTab(t: Tab) {
		const url = new URL(page.url);
		if (t === 'overview') url.searchParams.delete('tab');
		else url.searchParams.set('tab', t);
		goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	}

	const description = $derived(
		'One row per order with payment + customer. Joins cleaned staging orders to payments and customer attributes; promoted to the target table after audits pass.'
	);
	// keep the active tab valid when node type changes (e.g. a check has no Columns)
	$effect(() => {
		if (!tabs.some(([t]) => t === tab)) setTab(tabs[0]?.[0] ?? 'lineage');
	});
	let sqlMode = $state<'raw' | 'compiled'>('raw');
	let viewerMode = $state<'raw' | 'compiled' | 'diff' | 'drift'>('raw');
	const drift = $derived(MODEL_DRIFT[name]);
	function openSql() {
		viewerMode = sqlMode;
		setTab('sql');
	}

	// model facts (left column)
	const facts: [string, string][] = [
		['Duration', '0.04s'],
		['Rows', '1,284'],
		['Checks', '3/3'],
		['Freshness', 'within 1h']
	];

	// Definition rail (right) — static identity metadata, SQLBuild-specific
	const definition = $derived<[string, string][]>([
		['Type', nodeType],
		['Materialization', isModel ? 'table' : nodeType === 'source' ? 'external' : '—'],
		['Unique key', isModel ? 'order_id' : '—'],
		['Group', 'marts'],
		['Owner', '@analytics'],
		['Adapter', 'snowflake · prod'],
		['Target', `waffle_shop.prod.${name}`],
		['Fingerprint', 'a3f1…9c2']
	]);
	const defTags = ['finance', 'core'];

	// recent-updates sparkline: last N build outcomes
	type Spark = 'ok' | 'warn' | 'fail' | 'none';
	const sparkColor: Record<Spark, string> = {
		ok: 'var(--sb-success)',
		warn: 'var(--sb-warning)',
		fail: 'var(--sb-error)',
		none: 'var(--border-strong)'
	};
	// 40 recent runs (most recent on the right)
	const recent: Spark[] = Array.from({ length: 40 }, (_, i) => {
		if (i === 31) return 'warn';
		if (i === 38) return 'fail';
		if (i % 13 === 0 && i > 0) return 'warn';
		return 'ok';
	});

	// Python code for loaders/tasks/assets/udfs
	const pyCode = `from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext


@loader
def ${name}(ctx: LoaderContext):
    if ctx.current_cursor_value is None:
        return fetch_all()
    return fetch_since(ctx.current_cursor_value)`;
	const checkDef = `CHECK (
  name "${name}",
  severity error,
  description "Revenue in marts reconciles to source within 0.1%."
);

SELECT 1
FROM __ref("daily_revenue") d
JOIN __source("raw__payments") p ON ...
HAVING abs(sum(d.total) - sum(p.amount)) > sum(p.amount) * 0.001`;

	type Col = { name: string; type: string; desc: string; flags: string[] };
	const columns: Col[] = [
		{ name: 'order_id', type: 'BIGINT', desc: 'Primary key, one row per order', flags: ['pk', 'not_null', 'unique'] },
		{ name: 'customer_id', type: 'BIGINT', desc: 'FK to dim_customers', flags: ['not_null', 'rel'] },
		{ name: 'order_status', type: 'VARCHAR', desc: 'completed | pending | cancelled', flags: ['accepted_values'] },
		{ name: 'total_cents', type: 'INTEGER', desc: 'Order total in cents', flags: [] },
		{ name: 'payment_method', type: 'VARCHAR', desc: 'card | cash | voucher', flags: [] },
		{ name: 'ordered_at', type: 'TIMESTAMP', desc: 'Order creation time (UTC)', flags: ['not_null'] },
		{ name: 'is_first_order', type: 'BOOLEAN', desc: 'First order for this customer', flags: [] }
	];

	const upstream = ['stg_orders', 'stg_payments', 'stg_customers'];
	const downstream = ['dim_customers', 'customer_status', 'order_status_idx', 'hourly_order_act', 'daily_activity', 'hourly_activity_ctx'];

	const sqlRaw = $derived(mockModelSql(name, 'table', upstream, description));
	const sqlVersions = $derived(modelVersions(name, sqlRaw));

	// per-model SQL + column->expression maps for column<->SQL linkage in the
	// Column lineage tab (clicking a node shows that model's SQL + the column's
	// defining expression there).
	const modelSql: Record<string, string> = {
		raw__orders: `-- external source: raw__orders\nid, cust_id, status, created`,
		raw__payments: `-- external source: raw__payments\norder_id, amount_cents, method`,
		stg_orders: `SELECT\n  id        AS order_id,\n  cust_id   AS customer_id,\n  status    AS order_status\nFROM __source("raw__orders")`,
		stg_payments: `SELECT\n  order_id,\n  amount_cents,\n  method    AS payment_method\nFROM __source("raw__payments")`,
		fact_orders: sqlRaw,
		daily_revenue: `SELECT\n  date_trunc('day', o.ordered_at) AS revenue_date,\n  sum(o.total_cents)              AS total_revenue_cents\nFROM __ref("fact_orders") o\nGROUP BY 1`
	};
	const modelColExpr: Record<string, Record<string, string>> = {
		raw__orders: { id: 'id', cust_id: 'cust_id', status: 'status' },
		raw__payments: { order_id: 'order_id', amount_cents: 'amount_cents', method: 'method' },
		stg_orders: { order_id: 'id        AS order_id', customer_id: 'cust_id   AS customer_id', order_status: 'status    AS order_status' },
		stg_payments: { order_id: 'order_id', amount_cents: 'amount_cents', payment_method: 'method    AS payment_method' },
		fact_orders: { order_id: 'o.order_id', customer_id: 'o.customer_id', order_status: 'o.order_status', total_cents: 'coalesce(p.amount_cents, 0) AS total_cents', payment_method: 'p.payment_method', ordered_at: 'o.ordered_at' },
		daily_revenue: { revenue_date: "date_trunc('day', o.ordered_at) AS revenue_date", total_revenue_cents: 'sum(o.total_cents)              AS total_revenue_cents' }
	};

	type ModelRun = { id: string; job: string; status: 'ok' | 'fail' | 'warn'; when: string; exact: string; duration: string; rows: string; detail?: string };
	const modelRuns: ModelRun[] = [
		{ id: 'run-9d21', job: 'nightly_build', status: 'ok', when: '4m ago', exact: '2026-05-31 11:56', duration: '0.04s', rows: '1,284' },
		{ id: 'run-91cd', job: 'marts_only', status: 'ok', when: '1h ago', exact: '2026-05-31 10:31', duration: '0.05s', rows: '1,272' },
		{ id: 'run-2b70', job: 'nightly_build', status: 'fail', when: '3h ago', exact: '2026-05-31 09:00', duration: '0.08s', rows: '—', detail: 'Audit unique(order_id) returned 3 rows' },
		{ id: 'run-7a14', job: 'nightly_build', status: 'warn', when: '5h ago', exact: '2026-05-31 06:58', duration: '0.06s', rows: '1,260', detail: 'Source freshness threshold exceeded' },
		{ id: 'run-c40e', job: 'checks_only', status: 'ok', when: '18h ago', exact: '2026-05-30 18:12', duration: '0.05s', rows: '1,248' }
	];
	const runStatusColor: Record<string, string> = { ok: 'var(--sb-success)', fail: 'var(--sb-error)', warn: 'var(--sb-warning)' };
	const runStatusLabel: Record<string, string> = { ok: 'Success', fail: 'Failed', warn: 'Warning' };

	const checks = [
		{ name: 'not_null(order_id)', phase: 'pre-promotion' },
		{ name: 'unique(order_id)', phase: 'pre-promotion' },
		{ name: 'relationships(customer_id → dim_customers)', phase: 'pre-promotion' }
	];
	const nodeIcon: Record<NodeType, typeof IconType> = {
		model: Table2,
		source: Database,
		loader: Download,
		seed: Sprout,
		task: Workflow,
		asset: Box,
		check: ShieldCheck,
		udf: FunctionSquare
	};
	const Glyph = $derived(nodeIcon[nodeType]);
</script>

<AppTopbar title="Catalog">
	<Button variant="outline" size="sm">↻ Refresh</Button>
	<Button size="sm">▷ Execute</Button>
</AppTopbar>

<div class="asset-page">
	<header class="asset-header">
		<nav class="crumbs"><a href="/catalog">Catalog</a><span>/</span><span>{nodeType === 'model' ? 'Models' : nodeType[0].toUpperCase() + nodeType.slice(1) + 's'}</span></nav>
		<div class="title-row">
			<Glyph size={18} strokeWidth={1.75} />
			<h2>{name}</h2>
			<StatusLabel tone={nodeType === 'source' ? 'var(--sb-text-faint)' : headerStatus.tone} label={nodeType === 'source' ? 'External' : headerStatus.label} />
			<div class="header-actions">
				<a class="btn-ghost" href="/lineage">View in lineage</a>
			</div>
		</div>
		<div class="meta-row">
			<span>{nodeType}{isModel ? ' · table' : ''}</span><span>marts</span><span>@analytics</span><span>Built 4m ago</span>
		</div>
		<div class="tabs" role="tablist">
			{#each tabs as [t, lbl] (t)}
				<button role="tab" aria-selected={tab === t} class:on={tab === t} onclick={() => setTab(t)}>{lbl}</button>
			{/each}
		</div>
	</header>

	<div class="asset-body" class:fill={tab === 'lineage' || tab === 'collineage' || tab === 'sql'}>
		{#if tab === 'overview'}
			<div class="overview">
				<main class="overview-main">
					<section class="panel status-panel">
						<div class="status-top">
							<StatusLabel tone="var(--sb-success)" label={nodeType === 'source' ? 'Observed' : 'Materialized'} />
							<RelativeTime value="4m ago" exact="2026-05-31 11:56" />
							<a class="run-link" href="/runs/run-9d21">run-9d21 →</a>
						</div>
						<div class="stat-grid">
							{#each facts as [k, v] (k)}<div><span>{k}</span><b>{v}</b></div>{/each}
						</div>
						<div class="build-strip" title="Last {recent.length} builds">
							{#each recent as st, i (i)}<i style:background={sparkColor[st]}></i>{/each}
						</div>
						<div class="strip-caption"><span>Last {recent.length} builds</span><span>now</span></div>
						{#if drift}
							<button class="drift-hint" class:upstream={drift === 'upstream'} onclick={() => { viewerMode = 'drift'; setTab('sql'); }}>
								<GitCompareIcon size={14} />
								<span><b>Drift</b> · {drift === 'direct' ? 'Direct change' : drift === 'compiled' ? 'Compiled SQL differs' : 'Upstream changed'} since the last build</span>
								<em>View drift →</em>
							</button>
						{/if}
					</section>

					<section class="section">
						<h3>Description</h3>
						<p class="description">{description}</p>
					</section>

					{#if hasSql}
						<section class="section">
							<CodePreview file="{name}.sql" code={sqlRaw} bind:mode={sqlMode} maxLines={16} onOpen={openSql} />
						</section>
					{:else if isPython || nodeType === 'udf'}
						<section class="section">
							<CodePreview file="{name}.py" code={pyCode} language="text" maxLines={16} onOpen={() => setTab('code')} />
						</section>
					{/if}

					{#if isModel}
						<section class="section">
							<div class="section-head"><h3>Checks</h3><span>{checks.length} of {checks.length} passing</span></div>
							<div class="rows">
								{#each checks as c (c.name)}
									<div class="row"><StatusLabel tone="var(--sb-success)" label="Passed" /><code>{c.name}</code><span class="muted ml-auto">{c.phase}</span></div>
								{/each}
							</div>
						</section>
					{/if}

					{#if hasColumns}
						<section class="section">
							<div class="section-head"><h3>Columns</h3><button class="link" onclick={() => setTab('columns')}>All {columns.length} →</button></div>
							<div class="rows">
								{#each columns.slice(0, 5) as c (c.name)}
									<div class="row"><code>{c.name}</code><span class="muted">{c.desc}</span><code class="muted ml-auto">{c.type.toLowerCase()}</code></div>
								{/each}
							</div>
						</section>
					{/if}

					<section class="section deps">
						<div>
							<h3>Upstream <span>{upstream.length}</span></h3>
							{#each upstream as u (u)}<a href="/catalog/{u}">{u}</a>{/each}
						</div>
						<div>
							<h3>Downstream <span>{downstream.length}</span></h3>
							{#each downstream as d (d)}<a href="/catalog/{d}">{d}</a>{/each}
						</div>
					</section>
				</main>

				<aside class="overview-rail">
					<section>
						<h3>Definition</h3>
						<dl>
							{#each definition as [k, v] (k)}
								<div><dt>{k}</dt><dd class:mono={k === 'Target' || k === 'Fingerprint' || k === 'Unique key'} title={v}>{v}</dd></div>
							{/each}
						</dl>
					</section>
					<section>
						<h3>Tags</h3>
						<div class="flex flex-wrap gap-1">{#each defTags as t (t)}<span class="sb-tag">{t}</span>{/each}</div>
					</section>
					<section>
						<h3>Jobs</h3>
						<a class="job-row" href="/jobs/nightly_build"><span>nightly_build</span><small>daily 02:00</small></a>
						<a class="job-row" href="/jobs/marts_only"><span>marts_only</span><small>manual</small></a>
					</section>
				</aside>
			</div>
		{:else if tab === 'columns'}
			<table class="sb-list">
				<thead><tr><th>Column</th><th>Type</th><th>Description</th><th>Audits</th></tr></thead>
				<tbody>
					{#each columns as c (c.name)}
						<tr>
							<td><code>{c.name}</code></td>
							<td><code class="muted">{c.type.toLowerCase()}</code></td>
							<td class="muted">{c.desc}</td>
							<td><div class="flex flex-wrap gap-1">{#each c.flags as f (f)}<span class="sb-tag">{f}</span>{:else}<span class="muted">—</span>{/each}</div></td>
						</tr>
					{/each}
				</tbody>
			</table>
		{:else if tab === 'sql'}
			<SqlViewer {name} raw={sqlRaw} bind:mode={viewerMode} versions={sqlVersions} upstreamNote={drift === 'upstream' ? 'fact_orders changed since this model’s last build.' : undefined} onRef={(m) => (window.location.href = `/catalog/${m}?tab=sql`)} />
		{:else if tab === 'code'}
			<div class="p-5"><CodePreview file="{name}.py" code={pyCode} language="text" maxLines={200} /></div>
		{:else if tab === 'lineage'}
			<ScopedLineage focal={name} {graphNodes} {graphEdges} />
		{:else if tab === 'collineage'}
			<ColumnLineage focal={name} models={colModels} {colEdges} {modelSql} {modelColExpr} />
		{:else if tab === 'definition'}
			<div class="p-5"><CodePreview file="{name}.sql" code={checkDef} maxLines={200} /></div>
		{:else if tab === 'runs'}
			<table class="sb-list">
				<thead><tr><th>Run</th><th>Job</th><th class="num">Rows</th><th class="num">Duration</th><th>Started</th></tr></thead>
				<tbody>
					{#each modelRuns as r (r.id)}
						<tr onclick={() => (window.location.href = `/runs/${r.id}`)}>
							<td>
								<div class="run-cell"><StatusLabel tone={runStatusColor[r.status]} label={runStatusLabel[r.status]} /><code class="muted">{r.id}</code></div>
								{#if r.detail}<div class="run-detail" style:color={runStatusColor[r.status]}>{r.detail}</div>{/if}
							</td>
							<td><a class="link" href="/jobs/{r.job}" onclick={(e) => e.stopPropagation()}>{r.job}</a></td>
							<td class="num muted">{r.rows}</td>
							<td class="num muted">{r.duration}</td>
							<td><RelativeTime value={r.when} exact={r.exact} /></td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>

<style>
	.asset-page {
		display: flex;
		min-height: 0;
		flex: 1;
		flex-direction: column;
	}
	.asset-header {
		padding: 14px 24px 0;
		border-bottom: 1px solid var(--border);
	}
	.crumbs {
		display: flex;
		gap: 6px;
		color: var(--muted-foreground);
		font-size: 12.5px;
	}
	.crumbs a:hover {
		color: var(--foreground);
	}
	.title-row {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-top: 8px;
	}
	.title-row :global(svg) {
		color: var(--muted-foreground);
	}
	.title-row h2 {
		margin: 0 6px 0 0;
		font-size: 20px;
		font-weight: 600;
		letter-spacing: -0.01em;
	}
	.header-actions {
		display: flex;
		gap: 6px;
		margin-left: auto;
	}
	.btn-ghost {
		height: 30px;
		padding: 0 12px;
		border: 1px solid var(--border);
		border-radius: 2px;
		color: var(--foreground);
		font-size: 12.5px;
		line-height: 28px;
	}
	.btn-ghost:hover {
		background: var(--sb-hover);
	}
	.meta-row {
		display: flex;
		gap: 12px;
		margin-top: 6px;
		color: var(--muted-foreground);
		font-size: 12.5px;
	}
	.meta-row span + span::before {
		content: '·';
		margin-right: 12px;
		color: var(--sb-text-faint);
	}
	.tabs {
		display: flex;
		gap: 4px;
		margin-top: 14px;
	}
	.tabs button {
		position: relative;
		height: 38px;
		padding: 0 10px;
		border: 0;
		background: transparent;
		color: var(--muted-foreground);
		font-size: 13px;
	}
	.tabs button:hover {
		color: var(--foreground);
	}
	.tabs button.on {
		color: var(--foreground);
		font-weight: 500;
	}
	.tabs button.on::after {
		content: '';
		position: absolute;
		right: 6px;
		bottom: -1px;
		left: 6px;
		height: 2px;
		background: var(--primary);
	}
	.asset-body {
		min-height: 0;
		flex: 1;
		overflow: auto;
	}
	.asset-body.fill {
		display: flex;
		overflow: hidden;
	}
	.asset-body.fill > :global(*) {
		min-width: 0;
		flex: 1;
	}
	.overview {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 320px;
		min-height: 100%;
	}
	.overview-main {
		min-width: 0;
		padding: 20px 24px 48px;
	}
	.panel {
		padding: 16px;
		border: 1px solid var(--panel-border);
		box-shadow: var(--panel-shadow);
		border-radius: 2px;
		background: var(--card);
	}
	.status-top {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.run-link {
		margin-left: auto;
		color: var(--primary);
		font: 12px var(--font-mono);
	}
	.stat-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 16px;
		margin-top: 14px;
	}
	.stat-grid span {
		display: block;
		color: var(--muted-foreground);
		font-size: 12px;
	}
	.stat-grid b {
		font-size: 18px;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}
	.build-strip {
		display: flex;
		gap: 2px;
		height: 16px;
		margin-top: 16px;
	}
	.build-strip i {
		flex: 1;
		border-radius: 2px;
		opacity: 0.75;
	}
	.strip-caption {
		display: flex;
		justify-content: space-between;
		margin-top: 5px;
		color: var(--sb-text-faint);
		font-size: 11.5px;
	}
	.section {
		margin-top: 24px;
	}
	.section h3,
	.overview-rail h3 {
		margin: 0 0 8px;
		font-size: 13px;
		font-weight: 600;
	}
	.section h3 span {
		color: var(--muted-foreground);
		font-weight: 400;
	}
	.section-head {
		display: flex;
		align-items: baseline;
		margin-bottom: 8px;
	}
	.section-head h3 {
		margin: 0;
	}
	.section-head > span,
	.section-head .link {
		margin-left: auto;
		font-size: 12.5px;
	}
	.section-head > span {
		color: var(--muted-foreground);
	}
	.link {
		border: 0;
		background: transparent;
		color: var(--primary);
	}
	.description {
		max-width: 88ch;
		margin: 0;
		color: var(--muted-foreground);
		font-size: 13px;
		line-height: 1.55;
	}
	.rows {
		border: 1px solid var(--border);
		border-radius: 2px;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 14px;
		padding: 9px 14px;
		border-bottom: 1px solid var(--border);
		font-size: 12.5px;
	}
	.row:last-child {
		border-bottom: 0;
	}
	.row code {
		font: 12px var(--font-mono);
	}
	.muted {
		color: var(--muted-foreground);
	}
	.ml-auto {
		margin-left: auto;
	}
	.deps {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 24px;
	}
	.deps a {
		display: block;
		padding: 3px 0;
		color: var(--primary);
		font-size: 12.5px;
	}
	.deps a:hover {
		text-decoration: underline;
	}
	.overview-rail {
		padding: 20px;
		border-left: 1px solid var(--border);
	}
	.overview-rail section + section {
		margin-top: 22px;
	}
	.overview-rail dl {
		margin: 0;
	}
	.overview-rail dl > div {
		display: flex;
		gap: 12px;
		padding: 5px 0;
		font-size: 12.5px;
	}
	.overview-rail dt {
		flex: 0 0 auto;
		color: var(--muted-foreground);
	}
	.overview-rail dd {
		margin: 0 0 0 auto;
		overflow: hidden;
		text-align: right;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.overview-rail dd.mono {
		font: 12px var(--font-mono);
	}
	.job-row {
		display: flex;
		align-items: baseline;
		padding: 4px 0;
		font-size: 12.5px;
	}
	.job-row span {
		color: var(--primary);
	}
	.job-row small {
		margin-left: auto;
		color: var(--muted-foreground);
		font-size: 12px;
	}
	.run-cell {
		display: grid;
		grid-template-columns: 92px auto;
		align-items: center;
		gap: 10px;
	}
	.drift-hint {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 9px;
		margin-top: 14px;
		padding: 8px 10px;
		border: 1px solid color-mix(in srgb, var(--sb-stale) 35%, var(--border));
		border-radius: 2px;
		background: transparent;
		color: var(--foreground);
		font-size: 12.5px;
		text-align: left;
	}
	.drift-hint:hover {
		background: var(--sb-hover);
	}
	.drift-hint :global(svg) {
		flex: 0 0 auto;
		color: var(--sb-stale);
	}
	.drift-hint.upstream {
		border-style: dashed;
	}
	.drift-hint em {
		margin-left: auto;
		color: var(--primary);
		font-style: normal;
	}
	.run-detail {
		margin-top: 3px;
		font-size: 12px;
	}
</style>
