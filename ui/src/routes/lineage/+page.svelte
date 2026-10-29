<script lang="ts">
	import '@xyflow/svelte/dist/style.css';
	import { SvelteFlow, Background, Controls, type Node, type Edge } from '@xyflow/svelte';
	import AssetNode from '$lib/components/lineage/asset-node.svelte';
	import NodeFieldsPopover from '$lib/components/lineage/node-fields-popover.svelte';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import FocusIcon from '@lucide/svelte/icons/focus';
	import PanelLeftIcon from '@lucide/svelte/icons/panel-left';
	import PanelRightIcon from '@lucide/svelte/icons/panel-right';
	import SearchIcon from '@lucide/svelte/icons/search';
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right';
	import CopyIcon from '@lucide/svelte/icons/copy';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw';
	import { layoutGraph } from '$lib/lineage/layout';
	import { nodeFields } from '$lib/lineage/node-fields.svelte';
	import { neighbourEdgeIds, tracePath } from '$lib/lineage/trace';
	import { outlineSql } from '$lib/sql/outline';
	import { mockModelSql, modelVersions, MODEL_DRIFT } from '$lib/mock/model-sql';
	import GitCompareIcon from '@lucide/svelte/icons/git-compare';
	import SqlViewer from '$lib/components/code/sql-viewer.svelte';
	import CodePreview from '$lib/components/code/code-preview.svelte';
	import InspectorSection from '$lib/components/lineage/inspector-section.svelte';
	import Maximize2Icon from '@lucide/svelte/icons/maximize-2';
	import { tick, untrack } from 'svelte';
	import FlowController from '$lib/lineage/flow-controller.svelte';
	import RunPanel from '$lib/run/run-panel.svelte';
	import { page } from '$app/state';
	import { scaleGraph } from '$lib/mock/scale-graph';
	import { layoutDag } from '$lib/lineage/graph-layout';
	import { drawFar, hitTest } from '$lib/lineage/graph-draw';
	import type { Viewport } from '@xyflow/svelte';

	let runOpen = $state(false);
	let browserOpen = $state(false);
	let inspectorOpen = $state(true);
	let neighbourhoodOnly = $state(false);
	let modelQuery = $state('');

	const nodeTypes = { asset: AssetNode };

	// Positions are computed by dagre; start at 0,0 and let layout place them.
	const P = { x: 0, y: 0 };

	// drift is computed by the backend against the last build in this target
	const withDrift = (ns: Node[]) => ns.map((n) => (MODEL_DRIFT[n.id] ? { ...n, data: { ...n.data, drift: MODEL_DRIFT[n.id] } } : n));
	let nodes = $state.raw<Node[]>(withDrift([
		// sources
		{ id: 'raw_customers', type: 'asset', position: { ...P }, data: { name: 'raw__customers', kind: 'source', status: 'src', icon: 'source' } },
		{ id: 'raw_orders', type: 'asset', position: { ...P }, data: { name: 'raw__orders', kind: 'source · merge', status: 'src', icon: 'loader', freshness: '8m ago' } },
		{ id: 'raw_payments', type: 'asset', position: { ...P }, data: { name: 'raw__payments', kind: 'source', status: 'src', icon: 'source' } },
		{ id: 'load_cust', type: 'asset', position: { ...P }, data: { name: 'load__waffle_cust', kind: 'loader · table', status: 'ok', icon: 'loader', freshness: '8m ago' } },
		{ id: 'waffle_types', type: 'asset', position: { ...P }, data: { name: 'waffle_types', kind: 'seed', status: 'ok', icon: 'seed' } },
		// staging
		{ id: 'stg_customers', type: 'asset', position: { ...P }, data: { name: 'stg_customers', kind: 'view', status: 'ok', checks: '✓ 3', icon: 'view', freshness: '6m ago', columnCount: 5, description: 'Cleaned customers from raw.' } },
		{ id: 'stg_orders', type: 'asset', position: { ...P }, data: { name: 'stg_orders', kind: 'view', status: 'ok', checks: '✓ 4', icon: 'view', freshness: '6m ago', columnCount: 8, description: 'Cleaned orders from raw.' } },
		{ id: 'stg_payments', type: 'asset', position: { ...P }, data: { name: 'stg_payments', kind: 'view', status: 'stale', checks: '! 1', checksColor: 'var(--sb-warning)', icon: 'view', freshness: '6m ago', columnCount: 4, description: 'Cleaned payments from raw.' } },
		// marts mid
		{ id: 'daily_revenue', type: 'asset', position: { ...P }, data: { name: 'daily_revenue', kind: 'table', status: 'ok', checks: '✓ 1', icon: 'table', freshness: '6m ago', owner: '@analytics', description: 'Daily revenue rollup by completed orders.', columnCount: 3, tags: ['finance'] } },
		{ id: 'fact_orders', type: 'asset', selected: true, position: { ...P }, data: { name: 'fact_orders', kind: 'table', status: 'stale', checks: '✓ 1', icon: 'table', freshness: '4m ago', owner: '@analytics', description: 'One row per order with payment + customer.', columnCount: 7, tags: ['finance', 'core'] } },
		// right column
		{ id: 'dim_customers', type: 'asset', position: { ...P }, data: { name: 'dim_customers', kind: 'table', status: 'stale', checks: '✓ 2', icon: 'table', freshness: '4m ago', owner: '@analytics', description: 'Customer dimension with first/last order.', columnCount: 6, tags: ['core'] } },
		{ id: 'customer_status', type: 'asset', position: { ...P }, data: { name: 'customer_status', kind: 'incremental · merge', status: 'stale', checks: '✓ 2', icon: 'merge', freshness: '2d ago', owner: '@analytics', description: 'Upserted customer status snapshot.', columnCount: 4 } },
		{ id: 'order_status_idx', type: 'asset', position: { ...P }, data: { name: 'order_status_idx', kind: 'incremental · delete_insert', status: 'stale', icon: 'delete_insert', freshness: '5m ago', columnCount: 3 } },
		// far right
		{ id: 'hourly_order', type: 'asset', position: { ...P }, data: { name: 'hourly_order_act', kind: 'incremental · delete_insert', status: 'stale', icon: 'microbatch', freshness: '5m ago', columnCount: 5 } },
		{ id: 'daily_activity', type: 'asset', position: { ...P }, data: { name: 'daily_activity', kind: 'incremental · delete_insert', status: 'stale', checks: '✓ 2', icon: 'microbatch', freshness: '1d ago', columnCount: 4 } },
		{ id: 'hourly_ctx', type: 'asset', position: { ...P }, data: { name: 'hourly_activity_ctx', kind: 'incremental · delete_insert', status: 'fail', checks: '✕ 1', checksColor: 'var(--sb-error)', icon: 'microbatch', freshness: 'failed', columnCount: 6 } }
	]));

	const E = (s: string, t: string): Edge => ({
		id: `${s}-${t}`,
		source: s,
		target: t,
		type: 'bezier'
	});

	let edges = $state.raw<Edge[]>([
		E('raw_customers', 'stg_customers'),
		E('raw_orders', 'stg_orders'),
		E('raw_payments', 'stg_payments'),
		E('load_cust', 'stg_customers'),
		E('stg_customers', 'fact_orders'),
		E('stg_orders', 'fact_orders'),
		E('stg_payments', 'fact_orders'),
		E('stg_customers', 'daily_revenue'),
		E('fact_orders', 'dim_customers'),
		E('fact_orders', 'customer_status'),
		E('fact_orders', 'order_status_idx'),
		E('fact_orders', 'hourly_order'),
		E('fact_orders', 'daily_activity'),
		E('fact_orders', 'hourly_ctx')
	]);

	// Scale testing: /lineage?models=2000 swaps in a synthetic warehouse-shaped graph.
	// Positions are precomputed (stand-in for `sqb compile` output) instead of
	// running dagre in the browser, only on-screen cards are rendered, and when
	// zoomed out past the point where cards are legible a canvas draws the graph.
	const scaleModels = Number(page.url.searchParams.get('models') ?? 0);
	const scaleMode = scaleModels > 0;
	const FAR_ZOOM = 0.5;
	let scaleStartId = 'fact_orders';
	const scaleLayout = scaleMode ? (() => {
		const synthetic = scaleGraph(scaleModels);
		const t = performance.now();
		const layout = layoutDag(synthetic.nodes, synthetic.edges);
		const w = window as unknown as { __sbLayouts?: number[] };
		(w.__sbLayouts ??= []).push(performance.now() - t);
		nodes = synthetic.nodes.map((n) => {
			const g = layout.byId.get(n.id)!;
			return { ...n, position: { x: g.x, y: g.y }, hidden: true, initialWidth: 236, initialHeight: 61 };
		});
		scaleStartId =
			(nodes.find((n) => n.data.drift === 'direct' && /^(fct|dim|mart)/.test(String(n.data.name))) ??
				nodes.find((n) => n.data.drift === 'direct') ??
				nodes[nodes.length - 1]).id;
		nodes = nodes.map((n) => (n.id === scaleStartId ? { ...n, selected: true } : n));
		edges = synthetic.edges.map((e) => ({ ...e, hidden: true }));
		return layout;
	})() : null;

	let viewport = $state<Viewport>({ x: 0, y: 0, zoom: 1 });
	let farCanvas = $state<HTMLCanvasElement>();
	let graphPanel = $state<HTMLDivElement>();
	let panelSize = $state({ w: 0, h: 0 });
	const far = $derived(scaleMode && viewport.zoom < FAR_ZOOM);

	// Which cards exist in the page. Zoomed out: none (the canvas draws the graph).
	// Zoomed in: only cards within a quarter screen of the viewport, so cards far away
	// are never mounted (Svelte Flow force-renders any card it has not measured).
	let focusKeep = $state<Set<string> | null>(null);
	$effect(() => {
		if (!scaleLayout) return;
		const isFar = far;
		const { x, y, zoom } = viewport;
		const { w, h } = panelSize;
		const keep = focusKeep;
		untrack(() => {
			const mx = (w * 0.25) / zoom;
			const my = (h * 0.25) / zoom;
			const left = -x / zoom - mx;
			const right = (w - x) / zoom + mx;
			const top = -y / zoom - my;
			const bottom = (h - y) / zoom + my;
			const shown = new Set<string>();
			if (!isFar) {
				for (const g of scaleLayout.nodes) {
					if (keep && !keep.has(g.id)) continue;
					if (g.x + 236 >= left && g.x <= right && g.y + 61 >= top && g.y <= bottom) shown.add(g.id);
				}
			}
			if (nodes.some((n) => !!n.hidden === shown.has(n.id))) {
				nodes = nodes.map((n) => (!!n.hidden === shown.has(n.id) ? { ...n, hidden: !shown.has(n.id) } : n));
			}
			const edgeHidden = (e: Edge) => !(shown.has(e.source) && shown.has(e.target));
			if (edges.some((e) => !!e.hidden !== edgeHidden(e))) {
				edges = edges.map((e) => (!!e.hidden !== edgeHidden(e) ? { ...e, hidden: edgeHidden(e) } : e));
			}
		});
	});

	$effect(() => {
		if (!scaleLayout || !graphPanel) return;
		const ro = new ResizeObserver(([entry]) => {
			panelSize = { w: entry.contentRect.width, h: entry.contentRect.height };
		});
		ro.observe(graphPanel);
		return () => ro.disconnect();
	});

	$effect(() => {
		if (!scaleLayout || !farCanvas) return;
		const dpr = window.devicePixelRatio || 1;
		const { w, h } = panelSize;
		if (farCanvas.width !== Math.round(w * dpr)) farCanvas.width = Math.round(w * dpr);
		if (farCanvas.height !== Math.round(h * dpr)) farCanvas.height = Math.round(h * dpr);
		const ctx = farCanvas.getContext('2d');
		if (!ctx) return;
		if (!far) {
			ctx.clearRect(0, 0, farCanvas.width, farCanvas.height);
			return;
		}
		drawFar(ctx, { layout: scaleLayout, view: viewport, width: w, height: h, dpr, lit: lit?.nodes ?? null, selected: selectedIds });
	});

	// open on the whole graph: Svelte Flow's own initial fit waits for measured cards
	let setFlowViewport = $state<(v: Viewport) => void>();
	let didScaleFit = false;
	function fitScaleGraph() {
		if (!scaleLayout || !setFlowViewport || !panelSize.w) return;
		const pad = 24;
		const zoom = Math.min((panelSize.w - pad * 2) / scaleLayout.width, (panelSize.h - pad * 2) / scaleLayout.height);
		setFlowViewport({ zoom, x: (panelSize.w - scaleLayout.width * zoom) / 2, y: pad });
	}
	$effect(() => {
		if (!scaleMode || didScaleFit || !setFlowViewport || !panelSize.w) return;
		didScaleFit = true;
		fitScaleGraph();
	});

	function onFarClick({ event }: { event: MouseEvent }) {
		if (!far || !scaleLayout || !graphPanel) return;
		const rect = graphPanel.getBoundingClientRect();
		const hit = hitTest(event.clientX - rect.left, event.clientY - rect.top, scaleLayout, viewport);
		nodes = nodes.map((n) => (n.selected === (n.id === hit?.id) ? n : { ...n, selected: n.id === hit?.id }));
	}

	// --- selection + hover driven highlighting ---
	let hoveredId = $state<string | null>(null);

	// ids of currently-selected nodes (Svelte Flow sets node.selected)
	const selectedIds = $derived(new Set(nodes.filter((n) => n.selected).map((n) => n.id)));

	// the lit set: full upstream+downstream path of the selection, or
	// immediate neighbours of the hovered node when nothing is selected.
	const lit = $derived.by(() => {
		if (selectedIds.size > 0) {
			return tracePath(selectedIds, edges);
		}
		if (hoveredId) {
			return { nodes: new Set([hoveredId]), edges: neighbourEdgeIds(hoveredId, edges) };
		}
		return null;
	});

	const EDGE_NEUTRAL = 'stroke: var(--sb-edge); stroke-width: 1.5;';
	const EDGE_ON = 'stroke: var(--primary); stroke-width: 2;';
	const EDGE_DIM = 'stroke: var(--sb-edge-dim); stroke-width: 1.2;';

	// Apply highlight styling back into the bound arrays whenever the lit set
	// changes. Guarded so it doesn't fight drag/selection (only touches style
	// + a dimmed data flag, and only when those actually change).
	$effect(() => {
		const l = lit;
		let edgesChanged = false;
		const nextEdges = edges.map((e) => {
			const style = !l ? EDGE_NEUTRAL : l.edges.has(e.id) ? EDGE_ON : EDGE_DIM;
			const animated = !!l && l.edges.has(e.id) && selectedIds.size > 0;
			if (e.style !== style || e.animated !== animated) edgesChanged = true;
			return { ...e, style, animated };
		});
		if (edgesChanged) edges = nextEdges;

		let nodesChanged = false;
		const nextNodes = nodes.map((n) => {
			const dimmed = !!l && !l.nodes.has(n.id);
			if (n.data.dimmed !== dimmed) nodesChanged = true;
			return dimmed === n.data.dimmed ? n : { ...n, data: { ...n.data, dimmed } };
		});
		if (nodesChanged) nodes = nextNodes;
	});

	// the inspector reflects the current selection
	const selectedNodes = $derived(nodes.filter((n) => n.selected));
	// model names selected in the graph (falls back to the inspector's primary)
	// realistically nobody hand-picks >50; cap the manual selection (use a query beyond that)
	const runSelection = $derived(selectedNodes.slice(0, 50).map((n) => n.data.name as string));
	const primary = $derived(selectedNodes[0] ?? nodes.find((n) => n.id === scaleStartId));
	const primarySlug = $derived(primary?.data.name ?? '');
	const primaryStatus = $derived(String(primary?.data.status ?? 'src'));
	const primaryStatusLabel = $derived(
		primaryStatus === 'ok'
			? 'current'
			: primaryStatus === 'warn'
				? 'warning'
				: primaryStatus === 'stale'
					? 'stale'
					: primaryStatus === 'fail'
						? 'failed'
						: 'source'
	);
	const primaryStatusColor = $derived(
		primaryStatus === 'ok'
			? 'var(--sb-success)'
			: primaryStatus === 'warn'
				? 'var(--sb-warning)'
				: primaryStatus === 'stale'
					? 'var(--sb-stale)'
					: primaryStatus === 'fail'
						? 'var(--sb-error)'
						: 'var(--sb-text-faint)'
	);
	// sources/seeds/loaders have no model SQL
	const primaryKind = $derived(String(primary?.data.kind ?? '').toLowerCase());
	const hasSql = $derived(!/source|seed|loader/.test(primaryKind));
	const groupOf = (name: string) =>
		/^(raw__|load)/.test(name) || name === 'waffle_types' ? 'sources' : name.startsWith('stg_') ? 'staging' : 'marts';
	let collapsedGroups = $state<Set<string>>(new Set());
	function toggleGroup(g: string) {
		const next = new Set(collapsedGroups);
		next.has(g) ? next.delete(g) : next.add(g);
		collapsedGroups = next;
	}
	const browserGroups = $derived(
		['sources', 'staging', 'marts']
			.map((g) => ({ name: g, nodes: browserNodes.filter((n) => groupOf(String(n.data.name)) === g) }))
			.filter((g) => g.nodes.length)
	);
	const browserNodes = $derived(
		[...nodes]
			.filter((node) => String(node.data.name ?? '').toLowerCase().includes(modelQuery.trim().toLowerCase()))
			.sort((left, right) => String(left.data.name).localeCompare(String(right.data.name)))
	);

	// immediate upstream/downstream of the selected model (for the Lineage tab)
	const nameOf = (id: string) => nodes.find((n) => n.id === id)?.data.name ?? id;
	const upstream = $derived(primary ? edges.filter((e) => e.target === primary.id).map((e) => nameOf(e.source)) : []);
	const downstream = $derived(primary ? edges.filter((e) => e.source === primary.id).map((e) => nameOf(e.target)) : []);

	// --- mock model detail (Columns / SQL / Runs) ---
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
	const flagColor: Record<string, string> = {
		pk: 'var(--primary)',
		not_null: 'var(--sb-success)',
		unique: 'var(--sb-secondary)',
		rel: 'var(--sb-stale)',
		accepted_values: 'var(--sb-warning)'
	};

	let sqlMode = $state<'raw' | 'compiled'>('raw');
	const sqlRaw = $derived(mockModelSql(String(primary?.data.name ?? ''), String(primary?.data.kind ?? 'table'), upstream.map(String), String(primary?.data.description ?? primary?.data.name ?? '')));
	let sqlOpen = $state(false);
	let viewerMode = $state<'raw' | 'compiled' | 'diff' | 'drift'>('raw');
	const primaryDrift = $derived(primary ? (MODEL_DRIFT[primary.id] ?? (primary.data.drift as typeof MODEL_DRIFT[string] | undefined)) : undefined);
	const sqlVersions = $derived(modelVersions(String(primary?.data.name ?? ''), sqlRaw));
	const upstreamDriftNote = $derived(
		primaryDrift === 'upstream'
			? `${upstream.filter((u) => MODEL_DRIFT[String(nodes.find((n) => n.data.name === u)?.id)]).join(', ') || 'an upstream model'} changed since this model’s last build.`
			: undefined
	);
	const driftLabel: Record<string, string> = {
		direct: 'Direct change',
		compiled: 'Compiled SQL differs',
		upstream: 'Upstream changed'
	};
	const sqlOutline = $derived(outlineSql(sqlRaw));
	function openSql(mode: 'raw' | 'compiled' | 'diff' | 'drift' = sqlMode) {
		viewerMode = mode;
		sqlOpen = true;
	}
	function selectByName(name: string) {
		const id = nodes.find((node) => node.data.name === name)?.id;
		if (id) selectModel(id);
	}
	const checkRows = [
		{ name: 'not_null(order_id)', ok: true, phase: 'pre-promotion' },
		{ name: 'unique(order_id)', ok: true, phase: 'pre-promotion' },
		{ name: 'relationships(customer_id)', ok: true, phase: 'pre-promotion' }
	];
	const recentBuilds = ['ok', 'ok', 'ok', 'ok', 'warn', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'fail', 'ok', 'ok', 'ok', 'ok', 'ok', 'warn', 'ok', 'ok', 'ok', 'ok', 'ok'];

	type MiniRun = {
		id: string;
		job: string;
		status: 'ok' | 'fail' | 'warn';
		when: string;
		duration: string;
		barHeight: number;
		detail?: string;
	};
	const modelRuns: MiniRun[] = [
		{ id: 'run-9d21', job: 'nightly_build', status: 'ok', when: '4m ago', duration: '0.04s', barHeight: 10 },
		{ id: 'run-91cd', job: 'marts_only', status: 'ok', when: '1h ago', duration: '0.05s', barHeight: 12 },
		{ id: 'run-2b70', job: 'nightly_build', status: 'fail', when: '3h ago', duration: '0.08s', barHeight: 24, detail: 'Audit unique_order_id returned 3 rows' },
		{ id: 'run-7a14', job: 'nightly_build', status: 'warn', when: '5h ago', duration: '0.06s', barHeight: 16, detail: 'Source freshness threshold exceeded' },
		{ id: 'run-c40e', job: 'checks_only', status: 'ok', when: 'Yesterday', duration: '0.05s', barHeight: 12 }
	];
	const runStatusColor: Record<string, string> = {
		ok: 'var(--sb-success)',
		fail: 'var(--sb-error)',
		warn: 'var(--sb-warning)'
	};
	const runStatusLabel: Record<string, string> = { ok: 'Success', fail: 'Failed', warn: 'Warning' };

	async function selectModel(id: string) {
		neighbourhoodOnly = false;
		if (scaleLayout) {
			focusKeep = null;
			nodes = nodes.map((node) => (node.selected === (node.id === id) ? node : { ...node, selected: node.id === id }));
			const g = scaleLayout.byId.get(id);
			if (g && setFlowViewport) setFlowViewport({ zoom: 1, x: panelSize.w / 2 - (g.x + 118), y: panelSize.h / 2 - (g.y + 30) });
			return;
		}
		nodes = nodes.map((node) => ({ ...node, hidden: false, selected: node.id === id }));
		edges = edges.map((edge) => ({ ...edge, hidden: false }));
		await tick();
		fitFlow?.({ duration: 220 });
	}

	async function toggleNeighbourhood() {
		const focus = selectedNodes[0];
		if (!focus && !neighbourhoodOnly) return;
		neighbourhoodOnly = !neighbourhoodOnly;
		const keep = new Set<string>(focus ? [focus.id] : []);
		if (neighbourhoodOnly) {
			for (const edge of edges) {
				if (edge.source === focus?.id || edge.target === focus?.id) {
					keep.add(edge.source);
					keep.add(edge.target);
				}
			}
		}
		if (scaleMode) {
			focusKeep = neighbourhoodOnly ? keep : null;
			await tick();
			if (neighbourhoodOnly) fitFlow?.({ duration: 220 });
			return;
		}
		nodes = nodes.map((node) => ({ ...node, hidden: neighbourhoodOnly && !keep.has(node.id) }));
		edges = edges.map((edge) => ({
			...edge,
			hidden: neighbourhoodOnly && (!keep.has(edge.source) || !keep.has(edge.target))
		}));
		await tick();
		fitFlow?.({ duration: 220 });
	}

	// ---- resizable inspector width (transient, like the run-detail gutter) ----
	// Dagster-like: the inspector scales with the viewport (~34%), within bounds.
	const inspectorDefault = () =>
		typeof window === 'undefined' ? 560 : Math.round(Math.min(720, Math.max(460, window.innerWidth * 0.34)));
	let inspectorW = $state(inspectorDefault());
	let inspectorDragging = $state(false);
	function startInspector(e: PointerEvent) {
		inspectorDragging = true;
		(e.target as HTMLElement).setPointerCapture(e.pointerId);
	}
	function onInspector(e: PointerEvent) {
		if (!inspectorDragging) return;
		// dragging the left edge: width grows as the pointer moves left
		inspectorW = Math.min(Math.max(480, window.innerWidth * 0.55), Math.max(380, window.innerWidth - e.clientX));
	}
	function endInspector(e: PointerEvent) {
		if (inspectorDragging) tick().then(() => fitFlow?.({ duration: 200 }));
		inspectorDragging = false;
		try {
			(e.target as HTMLElement).releasePointerCapture(e.pointerId);
		} catch {}
	}

	// Auto-layout runs only when a *layout-relevant* signal changes:
	// Node fields toggling, or node heights changing (re-measure). It must NOT
	// run on plain position changes, otherwise dragging a node would be
	// instantly snapped back by dagre.
	let layoutKey = $derived(
		JSON.stringify(nodeFields.value) +
			'|' +
			nodes.map((n) => `${n.id}:${Math.round(n.measured?.height ?? 0)}`).join(',')
	);

	let lastLayoutKey = '';

	$effect(() => {
		const key = layoutKey; // track only field state + measured heights
		if (scaleMode || key === lastLayoutKey) return;
		const measured = nodes.every((n) => n.measured?.width && n.measured?.height);
		if (!measured) return;
		lastLayoutKey = key;
		const layoutStart = performance.now();
		nodes = layoutGraph(nodes, edges);
		const w = window as unknown as { __sbLayouts?: number[] };
		(w.__sbLayouts ??= []).push(performance.now() - layoutStart);
		tick().then(() => fitFlow?.({ duration: 0 }));
	});

	let fitFlow = $state<((opts?: { duration?: number }) => void) | undefined>();
	// refit the graph when side panels open/close so nodes never hide behind them
	let panelKey = '';
	$effect(() => {
		const key = `${browserOpen}|${inspectorOpen}|${sqlOpen}`;
		if (key === panelKey) return;
		const first = panelKey === '';
		panelKey = key;
		if (!first) tick().then(() => fitFlow?.({ duration: 200 }));
	});
	async function resetLayout() {
		neighbourhoodOnly = false;
		if (scaleLayout) {
			focusKeep = null;
			inspectorW = inspectorDefault();
			fitScaleGraph();
			return;
		}
		nodes = nodes.map((node) => ({ ...node, hidden: false }));
		edges = edges.map((edge) => ({ ...edge, hidden: false }));
		nodes = layoutGraph(nodes, edges);
		inspectorW = inspectorDefault();
		await tick();
		fitFlow?.();
	}
</script>

<AppTopbar title="Lineage">
	<Button variant="outline" size="sm">↻ Refresh</Button>
	<Button size="sm" onclick={() => (runOpen = true)}>▷ Execute</Button>
</AppTopbar>

<RunPanel bind:open={runOpen} selection={runSelection} />

<!-- filter toolbar -->
<div class="lineage-page">
	<section class="lineage-workbench">
<div class="lineage-toolbar">
	<button
		class="icon-toggle"
		class:active={browserOpen}
		onclick={() => (browserOpen = !browserOpen)}
		title={browserOpen ? 'Hide model list' : 'Show model list'}
		aria-label="Toggle model list"
	><PanelLeftIcon size={15} /></button>
	<div class="search-wrap">
		<label class="model-search">
			<SearchIcon size={14} />
			<input bind:value={modelQuery} placeholder="Search models" />
		</label>
		{#if modelQuery.trim() && !browserOpen}
			<div class="search-results">
				{#each browserNodes.slice(0, 8) as node (node.id)}
					<button onclick={() => { selectModel(node.id); modelQuery = ''; }}>
						<i class="browser-status {String(node.data.status)}"></i>
						<span>{node.data.name}</span>
						<small>{String(node.data.kind).split(' · ')[0]}</small>
					</button>
				{:else}
					<div class="browser-empty">No matching models</div>
				{/each}
			</div>
		{/if}
	</div>
	<div class="toolbar-group">
		{#each ['Kind', 'Group', 'Status'] as f (f)}
			<button class="toolbar-filter">{f} <ChevronDownIcon size={13} /></button>
		{/each}
	</div>
	<span class="toolbar-sep"></span>
	<NodeFieldsPopover />
	<button
		onclick={toggleNeighbourhood}
		class="toolbar-action"
		class:focus-active={neighbourhoodOnly}
		disabled={!neighbourhoodOnly && selectedNodes.length === 0}
		title={!neighbourhoodOnly && selectedNodes.length === 0 ? 'Select a model to focus on it' : 'Show only the selected model and its immediate dependencies'}
	>
		<FocusIcon size={14} /> {neighbourhoodOnly ? 'Show all' : 'Focus'}
	</button>
	<button onclick={resetLayout} class="toolbar-action" title="Reset layout"><RotateCcwIcon size={13} /> Reset</button>
	<div class="status-summary ml-auto">
		{#each [['ok', 'var(--sb-success)'], ['warn', 'var(--sb-warning)'], ['stale', 'var(--sb-stale)'], ['fail', 'var(--sb-error)']] as [st, c] (st)}
			{@const n = nodes.filter((x) => x.data.status === st).length}
			{#if n}<span><i style:background={c}></i>{n}</span>{/if}
		{/each}
	</div>
	<button
		class="icon-toggle"
		class:active={inspectorOpen}
		onclick={() => (inspectorOpen = !inspectorOpen)}
		title={inspectorOpen ? 'Hide details' : 'Show details'}
		aria-label="Toggle details"
	><PanelRightIcon size={15} /></button>
</div>

<div class="lineage-stage relative flex min-h-0 flex-1">
	{#if browserOpen}
		<aside class="model-browser">
			<div class="browser-heading">
				<span>Models</span>
				<b>{browserNodes.length}</b>
			</div>
			<div class="browser-list sb-scroll">
				{#each browserGroups as g (g.name)}
					<button class="browser-group" onclick={() => toggleGroup(g.name)} aria-expanded={!collapsedGroups.has(g.name)}>
						<ChevronRightIcon size={13} class={collapsedGroups.has(g.name) ? '' : 'rotate-90'} />
						<span>{g.name}</span><b>{g.nodes.length}</b>
					</button>
					{#if !collapsedGroups.has(g.name)}
						{#each g.nodes as node (node.id)}
							<button
								class="browser-row"
								class:selected={selectedIds.has(node.id)}
								onclick={() => selectModel(node.id)}
								title={String(node.data.name)}
							>
								<i class="browser-status {String(node.data.status)}"></i>
								<span><strong>{node.data.name}</strong></span>
							</button>
						{/each}
					{/if}
				{/each}
				{#if browserNodes.length === 0}
					<div class="browser-empty">No models match “{modelQuery}”.</div>
				{/if}
			</div>
		</aside>
	{/if}
	<!-- graph canvas -->
	<div class="graph-panel sb-flow relative min-w-0 flex-1 overflow-hidden" style="background: var(--sb-inset)" bind:this={graphPanel}>
		<SvelteFlow
			bind:nodes
			bind:edges
			{nodeTypes}
			fitView
			fitViewOptions={{ padding: 0.08, maxZoom: 1, includeHiddenNodes: scaleMode }}
			minZoom={scaleMode ? 0.02 : 0.3}
			onlyRenderVisibleElements={scaleMode}
			onpaneclick={onFarClick}
			elementsSelectable
			nodesDraggable
			multiSelectionKey={['Shift', 'Meta', 'Control']}
			selectionKey="Shift"
			proOptions={{ hideAttribution: true }}
			onnodepointerenter={({ node }) => (hoveredId = node.id)}
			onnodepointerleave={() => (hoveredId = null)}
		>
			<FlowController bind:fitView={fitFlow} bind:viewport bind:setViewport={setFlowViewport} />
			<Background gap={64} bgColor="var(--sb-inset)" patternColor="var(--sb-grid)" />
			<Controls />
		</SvelteFlow>
		{#if scaleMode}
			<canvas class="far-canvas" bind:this={farCanvas} style:width="{panelSize.w}px" style:height="{panelSize.h}px" style:display={far ? 'block' : 'none'}></canvas>
			<div class="scale-hint">{scaleModels.toLocaleString()} models · {far ? 'zoomed out: status overview' : 'cards'} · zoom {Math.round(viewport.zoom * 100)}%</div>
		{/if}
	</div>

	{#if sqlOpen && hasSql}
		<div class="sql-drawer">
			<SqlViewer name={String(primary?.data.name ?? '')} raw={sqlRaw} bind:mode={viewerMode} versions={sqlVersions} upstreamNote={upstreamDriftNote} onRef={selectByName} onClose={() => (sqlOpen = false)} />
		</div>
	{/if}

	<!-- inspector (resizable) -->
	{#if inspectorOpen}
	<div class="inspector-panel relative shrink-0" style:width="{inspectorW}px" class:select-none={inspectorDragging}>
	<!-- drag handle on the left edge -->
	<div
		class="sb-inspector-handle absolute left-0 top-0 bottom-0 z-30 -ml-1 w-2 cursor-col-resize"
		onpointerdown={startInspector}
		onpointermove={onInspector}
		onpointerup={endInspector}
		role="separator"
		aria-label="Resize inspector"
		title="Drag to resize"
		tabindex="-1"
	></div>
	<aside class="sb-scroll flex h-full w-full flex-col overflow-x-hidden overflow-y-auto border-l border-border bg-card">
		{#if selectedNodes.length > 1}
			<div class="border-b border-border p-4">
				<div class="text-[15px] font-semibold">{selectedNodes.length} models selected</div>
				<div class="text-[var(--sb-text-faint)] mt-1 text-[11.5px]">
					{selectedNodes.map((n) => n.data.name).slice(0, 3).join(', ')}{selectedNodes.length > 3 ? '…' : ''}
				</div>
			</div>
		{:else}
			<div class="inspector-head">
				<div class="flex items-center gap-2">
					<span class="truncate text-[15px] font-semibold">{primary?.data.name}</span>
					<a href="/catalog/{primarySlug}" class="head-link ml-auto" title="Open in Catalog">Catalog ↗</a>
				</div>
				<div class="inspector-meta">
					<span>{primary?.data.kind}</span>
					<span>marts</span>
					<span>@analytics</span>
				</div>
			</div>
		{/if}
		<div class="insp-body">
			{#if hasSql}
				<InspectorSection title="Latest build">
					{#snippet meta()}<a class="section-link" href="/runs/run-9d21">View run →</a>{/snippet}
					<div class="status-top">
						<span class="status-chip" style:--tone={primaryStatusColor}><i></i>{primaryStatus === 'ok' ? 'Materialized' : primaryStatusLabel.charAt(0).toUpperCase() + primaryStatusLabel.slice(1)}</span>
						<span class="status-when">{primary?.data.freshness ?? '—'}</span>
					</div>
					<div class="status-stats">
						<div><span>Duration</span><b>0.04s</b></div>
						<div><span>Rows</span><b>1,284</b><em class="up">+12</em></div>
						<div><span>Checks</span><b>{checkRows.filter((c) => c.ok).length}/{checkRows.length}</b></div>
					</div>
					<div class="build-strip" title="Last 24 builds">
						{#each recentBuilds as b, i (i)}<i class={b}></i>{/each}
					</div>
					<div class="build-strip-caption"><span>Last 24 builds</span><span>now</span></div>
					{#if primaryDrift}
						<button class="drift-hint {primaryDrift}" onclick={() => openSql('drift')}>
							<GitCompareIcon size={14} />
							<span><b>Drift</b> · {driftLabel[primaryDrift]} since the last build</span>
							<em>View drift →</em>
						</button>
					{/if}
					<dl class="kv">
						<div><dt>Run</dt><dd><a class="mono link" href="/runs/run-9d21">run-9d21</a></dd></div>
						<div><dt>Job</dt><dd><a class="link" href="/jobs/nightly_build">nightly_build</a> <span class="muted">· schedule</span></dd></div>
						<div><dt>Started</dt><dd>2026-05-31 11:56 <span class="muted">· {primary?.data.freshness ?? ''}</span></dd></div>
						<div><dt>Target</dt><dd class="mono">waffle_shop.prod.{primarySlug}</dd></div>
					</dl>
				</InspectorSection>
			{:else}
				<InspectorSection title="Source">
					<dl class="kv">
						<div><dt>Location</dt><dd class="mono">raw.{primary?.data.name}</dd></div>
						<div><dt>Freshness</dt><dd>{primary?.data.freshness ?? 'unknown'}</dd></div>
						<div><dt>Loaded by</dt><dd>external</dd></div>
					</dl>
				</InspectorSection>
			{/if}

			{#if primary?.data.description}
				<InspectorSection title="Description">
					<p class="insp-description">{primary.data.description}</p>
				</InspectorSection>
			{/if}

			{#if hasSql}
				<InspectorSection title="SQL">
					{#snippet meta()}<span>{sqlRaw.split('\n').length} lines</span><button class="section-link" onclick={() => openSql()}>Open →</button>{/snippet}
					<CodePreview file="{primarySlug}.sql" code={sqlRaw} bind:mode={sqlMode} maxLines={14} onOpen={() => openSql()} />
				</InspectorSection>
			{/if}

			<InspectorSection title="Checks">
				{#snippet meta()}<span>{checkRows.filter((c) => c.ok).length} of {checkRows.length} passing</span>{/snippet}
				{#each checkRows as c (c.name)}
					<div class="check-row">
						<i style:background={c.ok ? 'var(--sb-success)' : 'var(--sb-error)'}></i><code>{c.name}</code>
						<span>{c.phase}</span>
					</div>
				{/each}
			</InspectorSection>

			<InspectorSection title="Columns">
				{#snippet meta()}<a class="section-link" href="/catalog/{primarySlug}?tab=columns">All {columns.length} →</a>{/snippet}
				<dl class="kv">
					{#each columns.slice(0, 6) as c (c.name)}
						<div><dt class="mono fg">{c.name}</dt><dd class="muted">{c.desc}</dd><dd class="mono muted type">{c.type.toLowerCase()}</dd></div>
					{/each}
				</dl>
			</InspectorSection>

			<InspectorSection title="Recent runs">
				{#snippet meta()}<a class="section-link" href="/catalog/{primarySlug}?tab=runs">All →</a>{/snippet}
				{#each modelRuns.slice(0, 3) as run (run.id)}
					<a class="mini-run" href="/runs/{run.id}">
						<i style:background={runStatusColor[run.status]}></i>
						<span class="mini-run-main"><b>{runStatusLabel[run.status]}</b><span>{run.job}</span></span>
						<span class="mini-run-meta">{run.duration} · {run.when}</span>
						{#if run.detail}<em>{run.detail}</em>{/if}
					</a>
				{/each}
			</InspectorSection>

			<InspectorSection title="Dependencies">
				{#snippet meta()}<span>{upstream.length} up · {downstream.length} down</span>{/snippet}
				<div class="deps">
					<div>
						<div class="dep-head">Upstream</div>
						{#each upstream as model (model)}
							<button class="dependency-row" onclick={() => selectByName(String(model))}>{model}</button>
						{:else}<span class="section-meta">None</span>{/each}
					</div>
					<div>
						<div class="dep-head">Downstream</div>
						{#each downstream as model (model)}
							<button class="dependency-row" onclick={() => selectByName(String(model))}>{model}</button>
						{:else}<span class="section-meta">None</span>{/each}
					</div>
				</div>
			</InspectorSection>

			<InspectorSection title="Definition">
				<dl class="kv">
					{#each [['Materialized', sqlOutline.config.find((c) => c.key === 'materialized')?.value ?? 'table'], ['Unique key', sqlOutline.config.find((c) => c.key === 'unique_key')?.value ?? '—'], ['Group', 'marts'], ['Owner', '@analytics'], ['Tags', 'finance, core'], ['Fingerprint', 'a3f1…9c2']] as [k, v] (k)}
						<div><dt>{k}</dt><dd class:mono={k === 'Fingerprint' || k === 'Unique key'}>{v}</dd></div>
					{/each}
				</dl>
			</InspectorSection>
		</div>
	</aside>
	</div>
	{/if}
</div>
	</section>
</div>

<style>
	.far-canvas {
		position: absolute;
		inset: 0;
		z-index: 4;
		pointer-events: none;
	}
	.scale-hint {
		position: absolute;
		right: 12px;
		bottom: 10px;
		z-index: 5;
		font-size: 11px;
		color: var(--sb-text-faint);
		pointer-events: none;
	}
	.lineage-page {
		display: flex;
		min-height: 0;
		flex: 1;
		flex-direction: column;
	}
	.lineage-workbench {
		display: flex;
		min-height: 0;
		flex: 1;
		flex-direction: column;
		overflow: hidden;
		background: var(--card);
	}
	.lineage-stage {
		min-height: 0;
		flex: 1;
		overflow: hidden;
	}
	.lineage-toolbar {
		flex: 0 0 auto;
		gap: 5px;
		padding-top: 7px;
		padding-bottom: 7px;
	}
	.model-search {
		display: flex;
		width: 230px;
		height: 31px;
		align-items: center;
		gap: 7px;
		padding: 0 10px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--background);
		color: var(--sb-text-faint);
	}
	.model-search input {
		min-width: 0;
		flex: 1;
		border: 0;
		outline: 0;
		background: transparent;
		color: var(--foreground);
		font-size: 12px;
	}
	.model-search input::placeholder {
		color: var(--sb-text-faint);
	}
	.panel-toggle {
		display: flex;
		height: 31px;
		align-items: center;
		gap: 7px;
		padding: 0 10px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--card);
		color: var(--muted-foreground);
		font-size: 12px;
	}
	.panel-toggle:hover {
		background: var(--sb-hover);
		color: var(--foreground);
	}
	.panel-toggle.active,
	.focus-active {
		border-color: color-mix(in srgb, var(--primary) 28%, var(--border));
		background: var(--sidebar-accent);
		color: var(--primary);
	}
	.toolbar-filter,
	.toolbar-action {
		display: flex;
		height: 29px;
		align-items: center;
		gap: 5px;
		padding: 0 8px;
		border: 1px solid transparent;
		border-radius: 2px;
		background: transparent;
		color: var(--muted-foreground);
		font-size: 12px;
	}
	.toolbar-filter:hover,
	.toolbar-action:hover {
		background: var(--sb-hover);
		color: var(--foreground);
	}
	.status-summary {
		display: flex;
		align-items: center;
		gap: 12px;
		font: 11.5px var(--font-sans);
	}
	.status-summary span {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		white-space: nowrap;
	}
	.status-summary i {
		width: 6px;
		height: 6px;
		border-radius: 50%;
	}
	.model-browser {
		display: flex;
		width: 244px;
		flex: 0 0 244px;
		flex-direction: column;
		border-right: 1px solid var(--border);
		background: var(--card);
	}
	.browser-heading {
		display: flex;
		height: 37px;
		align-items: center;
		padding: 0 12px;
		border-bottom: 1px solid var(--border);
		color: var(--sb-text-faint);
		font: 500 11px var(--font-sans);
	}
	.browser-heading b {
		margin-left: auto;
		color: var(--muted-foreground);
		font-weight: 500;
	}
	.browser-list {
		min-height: 0;
		flex: 1;
		overflow-y: auto;
		padding: 6px;
	}
	.browser-row {
		display: flex;
		width: 100%;
		min-height: 43px;
		align-items: center;
		gap: 8px;
		padding: 6px 8px;
		border: 0;
		border-radius: 2px;
		background: transparent;
		text-align: left;
	}
	.browser-row:hover {
		background: var(--sb-hover);
	}
	.browser-row.selected {
		background: var(--sidebar-accent);
	}
	.browser-row > span {
		min-width: 0;
	}
	.browser-row strong,
	.browser-row strong {
		color: var(--foreground);
		font: 500 12.5px var(--font-sans);
	}
	.browser-status {
		width: 7px;
		height: 7px;
		flex: 0 0 7px;
		border-radius: 50%;
		background: var(--sb-text-faint);
	}
	.browser-status.ok { background: var(--sb-success); }
	.browser-status.warn { background: var(--sb-warning); }
	.browser-status.stale { background: var(--sb-stale); }
	.browser-status.fail { background: var(--sb-error); }
	.browser-empty {
		padding: 20px 10px;
		color: var(--sb-text-faint);
		font: 11.5px var(--font-sans);
		text-align: center;
	}
	.inspector-panel {
		height: 100%;
	}
	/* thin styled scrollbars */
	.sb-scroll {
		scrollbar-width: thin;
		scrollbar-color: var(--border-strong) transparent;
	}
	.sb-scroll::-webkit-scrollbar {
		width: 9px;
		height: 9px;
	}
	.sb-scroll::-webkit-scrollbar-track {
		background: transparent;
	}
	.sb-scroll::-webkit-scrollbar-thumb {
		background: var(--border-strong);
		border-radius: 2px;
		border: 2px solid transparent;
		background-clip: content-box;
	}
	.sb-scroll::-webkit-scrollbar-thumb:hover {
		background: var(--muted-foreground);
		background-clip: content-box;
	}
	/* inspector resize handle */
	.sb-inspector-handle::after {
		content: '';
		position: absolute;
		top: 0;
		bottom: 0;
		left: 50%;
		width: 1px;
		transform: translateX(-0.5px);
		background: transparent;
		transition: background 0.12s;
	}
	.sb-inspector-handle:hover::after,
	.sb-inspector-handle:active::after {
		background: var(--primary);
	}
	/* Dark theme for Svelte Flow chrome (controls/minimap) which ship light by default */
	.sb-flow :global(.svelte-flow__controls) {
		box-shadow: var(--sb-elev);
		border: 1px solid var(--border);
		border-radius: 2px;
		overflow: hidden;
	}
	.sb-flow :global(.svelte-flow__controls-button) {
		background: var(--card);
		border-bottom: 1px solid var(--border);
		color: var(--foreground);
		width: 30px;
		height: 30px;
	}
	.sb-flow :global(.svelte-flow__controls-button:hover) {
		background: var(--sb-hover, #1f2532);
	}
	.sb-flow :global(.svelte-flow__controls-button svg) {
		fill: var(--muted-foreground, #8d96ab);
	}
	.sb-flow :global(.svelte-flow__controls-button:hover svg) {
		fill: var(--foreground, #eaecf2);
	}
	.sb-flow :global(.svelte-flow__attribution) {
		display: none;
	}
	/* ---- Dagster-inspired refinement ---- */
	.lineage-page {
		--sb-edge: color-mix(in srgb, var(--foreground) 30%, transparent);
		--sb-edge-dim: color-mix(in srgb, var(--foreground) 9%, transparent);
		font-family: var(--font-sans);
	}
	.lineage-toolbar {
		display: flex;
		height: 46px;
		flex: 0 0 46px;
		align-items: center;
		gap: 4px;
		padding: 0 10px;
		border-bottom: 1px solid var(--border);
		background: var(--card);
	}
	.icon-toggle {
		display: grid;
		width: 30px;
		height: 30px;
		place-items: center;
		border: 0;
		border-radius: 2px;
		background: transparent;
		color: var(--muted-foreground);
	}
	.icon-toggle:hover {
		background: var(--sb-hover);
		color: var(--foreground);
	}
	.icon-toggle.active {
		background: var(--sb-hover);
		color: var(--foreground);
	}
	.search-wrap {
		position: relative;
		margin: 0 6px 0 2px;
	}
	.model-search {
		width: 260px;
		height: 30px;
		border-radius: 2px;
		background: var(--background);
	}
	.model-search input {
		font-size: 12.5px;
	}
	.search-results {
		position: absolute;
		z-index: 40;
		top: calc(100% + 4px);
		left: 0;
		width: 320px;
		padding: 4px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--popover, var(--card));
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
	}
	.search-results button {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 8px;
		padding: 6px 8px;
		border: 0;
		border-radius: 2px;
		background: transparent;
		color: var(--foreground);
		font-size: 12.5px;
		text-align: left;
	}
	.search-results button:hover {
		background: var(--sb-hover);
	}
	.search-results small {
		margin-left: auto;
		color: var(--sb-text-faint);
		font-size: 11px;
	}
	.toolbar-group {
		display: flex;
		gap: 2px;
	}
	.toolbar-sep {
		width: 1px;
		height: 18px;
		margin: 0 6px;
		background: var(--border);
	}
	.toolbar-filter,
	.toolbar-action {
		height: 30px;
		gap: 5px;
		padding: 0 9px;
		border: 0;
		border-radius: 2px;
		font-size: 12.5px;
	}
	.toolbar-filter :global(svg) {
		color: var(--sb-text-faint);
	}
	.focus-active {
		border: 0;
		background: var(--sb-hover);
		color: var(--foreground);
	}
	.status-summary {
		gap: 14px;
		margin-right: 8px;
		color: var(--muted-foreground);
		font: 500 12px var(--font-sans);
		font-variant-numeric: tabular-nums;
	}
	.status-summary i {
		width: 7px;
		height: 7px;
	}
	.model-browser {
		width: 232px;
		flex-basis: 232px;
	}
	.browser-heading {
		font: 600 12px var(--font-sans);
		color: var(--muted-foreground);
	}
	.browser-row {
		min-height: 32px;
		border-radius: 2px;
	}
	.browser-row strong {
		font: 500 12.5px var(--font-sans);
	}
	.inspector-head {
		padding: 14px 16px 12px;
		border-bottom: 1px solid var(--border);
	}
	.inspector-meta span + span::before {
		content: '·';
		margin-right: 12px;
		color: var(--sb-text-faint);
	}
	.inspector-meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 12px;
		margin-top: 6px;
		color: var(--muted-foreground);
		font-size: 12px;
	}
	.head-link {
		flex: 0 0 auto;
		padding: 3px 8px;
		border: 1px solid var(--border);
		border-radius: 2px;
		color: var(--muted-foreground);
		font-size: 12px;
	}
	.head-link:hover {
		background: var(--sb-hover);
		color: var(--foreground);
	}
	.check-row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 5px 0;
		border-bottom: 1px solid var(--border-subtle);
		font-size: 12.5px;
	}
	.check-row:last-child {
		border-bottom: 0;
	}
	.check-row i {
		width: 7px;
		height: 7px;
		flex: 0 0 7px;
		border-radius: 50%;
	}
	.check-row code {
		font: 12px var(--font-mono);
	}
	.check-row span {
		margin-left: auto;
		color: var(--muted-foreground);
		font-size: 11.5px;
	}
	.sb-flow :global(.svelte-flow__controls) {
		box-shadow: none;
		border-radius: 2px;
	}
	.sb-flow :global(.svelte-flow__controls-button) {
		width: 28px;
		height: 28px;
	}
	.insp-body {
		display: flex;
		flex-direction: column;
	}
	.mini-run {
		display: grid;
		grid-template-columns: 8px 1fr auto;
		align-items: center;
		column-gap: 10px;
		padding: 7px 0;
		border-bottom: 1px solid var(--border-subtle);
		font-size: 12.5px;
	}
	.mini-run:last-child {
		border-bottom: 0;
	}
	.mini-run:hover .mini-run-main b {
		color: var(--primary);
	}
	.mini-run i {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}
	.mini-run-main b {
		margin-right: 8px;
		font-weight: 500;
	}
	.mini-run-main span,
	.mini-run-meta {
		color: var(--muted-foreground);
	}
	.mini-run-meta {
		font-size: 12px;
		font-variant-numeric: tabular-nums;
	}
	.mini-run em {
		grid-column: 2 / 4;
		margin-top: 2px;
		overflow: hidden;
		color: var(--sb-error);
		font-size: 12px;
		font-style: normal;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	/* ---- inspector summary v2 ---- */
	.insp-section {
		padding: 14px 16px;
		border-bottom: 1px solid var(--border);
	}
	.insp-description {
		margin: 0;
		color: var(--muted-foreground);
		font-size: 13px;
		line-height: 1.5;
	}
	.section-meta {
		color: var(--muted-foreground);
		font-size: 12px;
		font-weight: 400;
	}
	.section-link {
		margin-left: auto;
	}
	.section-link {
		border: 0;
		background: transparent;
		color: var(--primary);
		font-size: 12px;
	}
	.section-link:hover {
		text-decoration: underline;
	}
	.status-top {
		display: flex;
		align-items: center;
		gap: 10px;
		font-size: 12.5px;
	}
	.status-chip {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		color: var(--foreground);
		font-weight: 600;
	}
	.status-chip i {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--tone);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--tone) 20%, transparent);
	}
	.status-when {
		color: var(--muted-foreground);
	}
	.status-run {
		margin-left: auto;
		color: var(--primary);
		font: 12px var(--font-mono);
	}
	.status-stats {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 12px;
		margin-top: 14px;
	}
	.status-stats span {
		display: block;
		color: var(--muted-foreground);
		font-size: 11.5px;
	}
	.status-stats b {
		font-size: 16px;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}
	.status-stats em {
		margin-left: 6px;
		font-size: 11.5px;
		font-style: normal;
	}
	.status-stats em.up {
		color: var(--sb-success);
	}
	.build-strip {
		display: flex;
		gap: 2px;
		height: 14px;
		margin-top: 14px;
	}
	.build-strip i {
		flex: 1;
		border-radius: 2px;
		background: var(--sb-success);
		opacity: 0.7;
	}
	.build-strip i.warn {
		background: var(--sb-warning);
	}
	.build-strip i.fail {
		background: var(--sb-error);
	}
	.build-strip-caption {
		display: flex;
		justify-content: space-between;
		margin-top: 5px;
		color: var(--sb-text-faint);
		font-size: 11px;
	}
	.deps {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 16px;
	}
	.dependency-row {
		display: block;
		width: 100%;
		overflow: hidden;
		border: 0;
		background: transparent;
		font-size: 12.5px;
		text-align: left;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.deps .dependency-row {
		padding: 3px 0;
		color: var(--foreground);
	}
	.deps .dependency-row:hover {
		background: transparent;
		color: var(--primary);
	}
	.check-row span {
		font-size: 11.5px;
	}
	/* ---- SQL viewer drawer + SQL tab outline ---- */
	.sql-drawer {
		position: absolute;
		z-index: 30;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(1040px, 66%);
		border-left: 1px solid var(--border);
		box-shadow: -18px 0 40px rgba(0, 0, 0, 0.22);
		animation: drawer-in 0.16s ease-out;
	}
	@keyframes drawer-in {
		from {
			transform: translateX(24px);
			opacity: 0;
		}
	}
	/* ---- inspector v3: collapsible sections, key/value rows ---- */
	.kv {
		margin: 12px 0 0;
	}
	:global(.insp-sec-body > .kv:first-child) {
		margin-top: 0;
	}
	.kv > div {
		display: grid;
		grid-template-columns: 110px minmax(0, 1fr) auto;
		align-items: baseline;
		gap: 12px;
		padding: 6px 0;
		border-top: 1px solid var(--border-subtle);
		font-size: 12.5px;
	}
	.kv > div:first-child {
		border-top: 0;
	}
	.kv dt {
		overflow: hidden;
		color: var(--muted-foreground);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.kv dd {
		min-width: 0;
		margin: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.kv .mono {
		font: 12px var(--font-mono);
	}
	.kv .fg {
		color: var(--foreground);
	}
	.kv .muted,
	.insp-body .muted {
		color: var(--muted-foreground);
	}
	.kv .type {
		text-align: right;
	}
	.kv:has(.type) > div {
		grid-template-columns: 130px minmax(0, 1fr) auto;
	}
	.insp-body .link {
		color: var(--primary);
	}
	.insp-body .link:hover {
		text-decoration: underline;
	}
	.dep-head {
		margin-bottom: 4px;
		color: var(--muted-foreground);
		font-size: 12px;
	}
	.browser-group {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 6px;
		margin-top: 6px;
		padding: 5px 6px;
		border: 0;
		border-radius: 2px;
		background: transparent;
		color: var(--muted-foreground);
		font-size: 12px;
		font-weight: 600;
		text-transform: capitalize;
	}
	.browser-group:first-child {
		margin-top: 0;
	}
	.browser-group:hover {
		background: var(--sb-hover);
		color: var(--foreground);
	}
	.browser-group b {
		margin-left: auto;
		font-weight: 400;
	}
	.browser-group :global(svg) {
		transition: transform 0.15s;
	}
	.browser-group + .browser-row,
	.browser-row {
		padding-left: 24px;
	}
	.drift-hint {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 9px;
		margin-top: 12px;
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
	.drift-hint b {
		font-weight: 600;
	}
	.drift-hint em {
		margin-left: auto;
		color: var(--primary);
		font-style: normal;
		white-space: nowrap;
	}
	.toolbar-action:disabled {
		opacity: 0.45;
		pointer-events: none;
	}
	@media (max-width: 1450px) {
		.model-search {
			width: 200px;
		}
	}
</style>
