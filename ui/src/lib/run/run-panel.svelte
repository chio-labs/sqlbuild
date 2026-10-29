<script lang="ts">
	// Run panel (launchpad), "smart command line" spine: ONE editable command is
	// the interface. Autocomplete is the single way to add anything — type `--`
	// for flags (typed, with descriptions, per verb), or a bare token for selector
	// completion (model / tag: / path-between). The graph inserts selector tokens.
	// The typed config form is the one structured panel (per-run provider overrides).
	import ConfigForm, { type Field } from '$lib/config/config-form.svelte';
	import { goto } from '$app/navigation';
	import XIcon from '@lucide/svelte/icons/x';

	let {
		open = $bindable(false),
		selection = []
	}: { open?: boolean; selection?: string[] } = $props();

	type Verb = 'build' | 'test' | 'diff' | 'run-scenario';
	const verbs: Verb[] = ['build', 'test', 'diff', 'run-scenario'];
	let verb = $state<Verb>('build');

	// ---- flag schema, per verb (the autocomplete source) ----
	type FlagDef = { flag: string; type: 'bool' | 'string' | 'int' | 'date'; desc: string };
	const flagsByVerb: Record<Verb, FlagDef[]> = {
		build: [
			{ flag: '--select', type: 'string', desc: 'Selector expression (+model, tag:x, a~b)' },
			{ flag: '--exclude', type: 'string', desc: 'Exclude selector' },
			{ flag: '--full-refresh', type: 'bool', desc: 'Rebuild from scratch' },
			{ flag: '--defer-to', type: 'string', desc: 'Defer unselected refs to a target' },
			{ flag: '--start-cursor-ts', type: 'date', desc: 'Incremental: start timestamp' },
			{ flag: '--dry-run', type: 'bool', desc: 'Plan only, do not execute' },
			{ flag: '--fail-fast', type: 'bool', desc: 'Stop on first failure' },
			{ flag: '--threads', type: 'int', desc: 'Concurrency override' },
			{ flag: '--var', type: 'string', desc: 'key=value variable' }
		],
		test: [
			{ flag: '--select', type: 'string', desc: 'Selector for tests' },
			{ flag: '--unit', type: 'bool', desc: 'Unit tests only' },
			{ flag: '--scenario', type: 'bool', desc: 'Scenario tests only' }
		],
		diff: [
			{ flag: '--limit', type: 'int', desc: 'Row sample limit' },
			{ flag: '--schema-only', type: 'bool', desc: 'Schema diff only' }
		],
		'run-scenario': [{ flag: '--replay', type: 'bool', desc: 'Replay captured fixtures locally' }]
	};

	// ---- node metadata (mock; in prod the API resolves selectors) ----
	type NodeKind = 'source' | 'view' | 'table' | 'incremental' | 'task' | 'asset' | 'loader';
	type NodeMeta = { name: string; kind: NodeKind; group: string; status: 'ok' | 'stale' | 'warn' | 'fail' | 'src'; tags: string[]; providers: string[] };
	const NODES: NodeMeta[] = [
		{ name: 'raw__orders', kind: 'source', group: 'sources', status: 'src', tags: [], providers: [] },
		{ name: 'stg_orders', kind: 'view', group: 'staging', status: 'ok', tags: [], providers: [] },
		{ name: 'stg_payments', kind: 'view', group: 'staging', status: 'warn', tags: [], providers: [] },
		{ name: 'fact_orders', kind: 'table', group: 'marts', status: 'ok', tags: ['finance', 'core'], providers: [] },
		{ name: 'daily_revenue', kind: 'table', group: 'marts', status: 'ok', tags: ['finance', 'revenue'], providers: [] },
		{ name: 'dim_customers', kind: 'table', group: 'marts', status: 'ok', tags: ['core'], providers: [] },
		{ name: 'customer_status', kind: 'incremental', group: 'marts', status: 'stale', tags: [], providers: [] },
		{ name: 'load_raw_orders', kind: 'loader', group: 'sources', status: 'ok', tags: ['ingest'], providers: ['orders_api'] },
		{ name: 'export_revenue_csv', kind: 'task', group: 'exports', status: 'ok', tags: ['export'], providers: ['s3_archive'] },
		{ name: 'revenue_dashboard', kind: 'asset', group: 'bi', status: 'ok', tags: ['bi'], providers: ['slack_alerts'] }
	];
	const allModels = NODES.map((n) => n.name);
	const allTags = [...new Set(NODES.flatMap((n) => n.tags))].map((t) => `tag:${t}`);
	const allGroups = [...new Set(NODES.map((n) => n.group))].map((g) => `group:${g}`);
	const allKinds = [...new Set(NODES.map((n) => n.kind))].map((k) => `kind:${k}`);
	const allStatuses = ['status:ok', 'status:stale', 'status:warn', 'status:fail'];

	// ---- selector query (editable; seeded from the graph selection) ----
	let selectQuery = $state('');
	$effect(() => {
		// seed from graph selection, but only the names (capped); large selections
		// keep the full list under the hood while nudging toward a query
		if (open && !selectTouched) selectQuery = selection.join(' ');
	});
	let selectTouched = $state(false);
	$effect(() => {
		if (!open) selectTouched = false;
	});

	// tiny selector evaluator (mock; prod = debounced API). Supports
	// model names, tag:/group:/kind:/status:, *, and whitespace = OR.
	function matchesTerm(n: NodeMeta, term: string): boolean {
		const t = term.replace(/^\++|\++$/g, '').replace(/~.*/, ''); // strip graph ops for matching
		if (!t || t === '*') return true;
		if (t.startsWith('tag:')) return n.tags.includes(t.slice(4));
		if (t.startsWith('group:')) return n.group === t.slice(6);
		if (t.startsWith('kind:')) return n.kind === t.slice(5);
		if (t.startsWith('status:')) return n.status === t.slice(7);
		return n.name === t || n.name.includes(t);
	}
	const matched = $derived.by(() => {
		const q = selectQuery.trim();
		if (!q) return NODES; // empty select = whole project
		// tokens are whitespace-separated; 'and'/'or' are operators we treat as OR (mock)
		const terms = q.split(/\s+/).filter((t) => t && t !== 'and' && t !== 'or');
		if (!terms.length) return NODES;
		return NODES.filter((n) => terms.some((term) => matchesTerm(n, term)));
	});
	// manual selection ceiling — realistically nobody hand-picks more; beyond this
	// you use a query. We display up to this many chips, then "+N more".
	const SELECT_CAP = 50;

	// ---- target: locked to the project adapter (no switcher) ----
	const target = 'snowflake_prod';

	// ---- providers relevant to the selection (tasks/assets/loaders/hooks) ----
	const relevantProviders = $derived([...new Set(matched.flatMap((n) => n.providers))]);
	// per-provider config schema (mock)
	const providerSchema: Record<string, Field[]> = {
		orders_api: [
			{ key: 'base_url', type: 'string', default: 'https://api.example.com', description: 'API base URL' },
			{ key: 'page_size', type: 'int', default: 500, min: 1, max: 5000, description: 'Records per request' }
		],
		s3_archive: [
			{ key: 'bucket', type: 'string', default: 'example-datalake', description: 'S3 bucket' },
			{ key: 'prefix', type: 'string', default: 'exports/', description: 'Key prefix' }
		],
		slack_alerts: [{ key: 'channel', type: 'string', default: '#data-alerts', description: 'Target channel' }]
	};
	let cfgValues = $state<Record<string, Record<string, unknown>>>({});
	// ensure a values bucket exists for each relevant provider (no mutation in markup)
	$effect(() => {
		let changed = false;
		const next = { ...cfgValues };
		for (const p of relevantProviders) if (!next[p]) { next[p] = {}; changed = true; }
		if (changed) cfgValues = next;
	});
	const cfgErrors = $state(0);

	// ---- the command (single source of truth) ----
	let cmd = $state('');
	let cmdEl: HTMLInputElement | undefined = $state();

	// seed the command when opened / when selection or verb changes (only if the
	// command still looks "generated", i.e. the user hasn't taken it over)
	let userEdited = $state(false);
	const seed = $derived(`sqb ${verb}${selectQuery.trim() ? ` --select ${selectQuery.trim()}` : ''} --target ${target}`);
	$effect(() => {
		if (open && !userEdited) cmd = seed;
	});
	// reset takeover when panel closes
	$effect(() => {
		if (!open) userEdited = false;
	});

	// ---- autocomplete ----
	let acOpen = $state(false);
	let acIndex = $state(0);

	// the token the caret is in
	function currentToken(): { start: number; text: string } {
		const caret = cmdEl?.selectionStart ?? cmd.length;
		const before = cmd.slice(0, caret);
		const start = before.lastIndexOf(' ') + 1;
		return { start, text: cmd.slice(start, caret) };
	}

	const suggestions = $derived.by(() => {
		if (!acOpen) return [];
		const { text } = tokenState;
		if (text.startsWith('--')) {
			return flagsByVerb[verb]
				.filter((f) => f.flag.startsWith(text) && !cmd.includes(f.flag + ' ') && !cmd.endsWith(f.flag))
				.map((f) => ({ value: f.flag, label: f.flag, hint: `${f.type} · ${f.desc}` }));
		}
		// bare token → selector completion (attributes + models), honoring +/~ prefixes
		const m = text.match(/^([+]*)(.*)$/);
		const prefix = m?.[1] ?? '';
		const body = m?.[2] ?? '';
		const pool = [...allTags, ...allGroups, ...allKinds, ...allStatuses, ...allModels];
		return pool
			.filter((p) => p.toLowerCase().includes(body.toLowerCase()) && body.length > 0)
			.slice(0, 10)
			.map((p) => ({ value: prefix + p, label: prefix + p, hint: p.includes(':') ? p.split(':')[0] : 'model' }));
	});
	// track token reactively
	let tokenState = $state<{ start: number; text: string }>({ start: 0, text: '' });
	function refreshToken() {
		tokenState = currentToken();
		acOpen = tokenState.text.length > 0 && (tokenState.text.startsWith('--') || tokenState.text.length >= 1);
		acIndex = 0;
	}

	function applySuggestion(value: string) {
		const { start } = tokenState;
		const caret = cmdEl?.selectionStart ?? cmd.length;
		cmd = cmd.slice(0, start) + value + ' ' + cmd.slice(caret);
		userEdited = true;
		acOpen = false;
		queueMicrotask(() => cmdEl?.focus());
	}

	function onKeydown(e: KeyboardEvent) {
		if (!acOpen || suggestions.length === 0) return;
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			acIndex = (acIndex + 1) % suggestions.length;
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			acIndex = (acIndex - 1 + suggestions.length) % suggestions.length;
		} else if (e.key === 'Enter' || e.key === 'Tab') {
			e.preventDefault();
			applySuggestion(suggestions[acIndex].value);
		} else if (e.key === 'Escape') {
			acOpen = false;
		}
	}

	// per-run provider config overrides (vs schema defaults) → command suffix
	const overrideArgs = $derived(
		relevantProviders.flatMap((p) =>
			(providerSchema[p] ?? [])
				.filter((f) => cfgValues[p]?.[f.key] !== undefined && cfgValues[p][f.key] !== f.default)
				.map((f) => `--provider-config ${p}.${f.key}=${cfgValues[p][f.key]}`)
		)
	);

	function run() {
		open = false;
		goto('/runs/run-new');
	}
</script>

{#if open}
	<button class="fixed inset-0 z-40 bg-black/40" aria-label="Close" onclick={() => (open = false)}></button>
	<div class="bg-card fixed inset-x-0 bottom-0 z-50 flex max-h-[80vh] flex-col rounded-t-[2px] border-t border-border" style="box-shadow:var(--sb-elev)">
		<!-- header: verb -->
		<div class="flex items-center gap-3 border-b border-border px-6 py-3.5">
			<span class="font-display text-[15px] font-semibold">Run</span>
			<div class="flex overflow-hidden rounded-md border border-border">
				{#each verbs as v (v)}
					<button class="border-r border-border px-3 py-1 text-[11.5px] last:border-r-0 {verb === v ? 'bg-[var(--sidebar-accent)] text-foreground' : 'text-muted-foreground hover:bg-[var(--sb-hover)]'}" onclick={() => (verb = v)}>{v}</button>
				{/each}
			</div>
			<span class="text-[var(--sb-text-faint)] text-[11.5px]">target <span class="text-foreground">{target}</span> 🔒</span>
			<button class="text-muted-foreground hover:text-foreground ml-auto" onclick={() => (open = false)} aria-label="Close"><XIcon size={16} /></button>
		</div>

		<div class="grid min-h-0 flex-1 grid-cols-[1fr_360px]">
			<!-- left: selection result + scoped provider config -->
			<div class="sb-scroll overflow-auto border-r border-border px-6 py-4">
				<!-- selection: editable selector query + count + preview (scale-safe) -->
				<div class="mb-5">
					<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Selection</div>
					<div class="bg-secondary mb-2 flex items-center gap-2 rounded-md border border-border px-2.5 py-1.5">
						<span class="text-[var(--sb-text-faint)] text-[11px]">⌕</span>
						<input
							bind:value={selectQuery}
							oninput={() => {
								selectTouched = true;
								userEdited = false;
							}}
							placeholder="select: +fact_orders, tag:revenue, group:marts, *"
							class="text-foreground placeholder:text-[var(--sb-text-faint)] w-full bg-transparent text-[12px] outline-none"
						/>
						{#if selectQuery}<button class="text-[var(--sb-text-faint)] hover:text-foreground text-[11px]" onclick={() => { selectQuery = ''; selectTouched = true; userEdited = false; }}>✕</button>{/if}
					</div>
					<div class="flex items-center gap-2">
						<span class="text-[13px]">
							<span class="text-foreground font-medium">{matched.length}</span> node{matched.length === 1 ? '' : 's'} match
						</span>
						<span class="text-[var(--sb-text-faint)] text-[11px]">{selectQuery ? '' : 'whole project'}</span>
					</div>
					{#if matched.length}
						<!-- resolved selection as wrapping chips (capped height) -->
						<div class="sb-scroll mt-2 flex max-h-[88px] flex-wrap gap-1.5 overflow-auto">
							{#each matched.slice(0, SELECT_CAP) as n (n.name)}
								<span class="sb-tag code">{n.name}</span>
							{/each}
							{#if matched.length > SELECT_CAP}
								<span class="text-[var(--sb-text-faint)] self-center text-[11px]">+{matched.length - SELECT_CAP} more — refine with a query</span>
							{/if}
						</div>
					{/if}
				</div>

				<!-- provider config: only the providers the selection actually uses -->
				<div class="text-[var(--sb-text-faint)] mb-2 flex items-center justify-between text-[12px] font-medium">
					<span>Provider config</span>
					<a href="/providers" class="text-[var(--sb-text-faint)] hover:text-primary normal-case tracking-normal">durable config →</a>
				</div>
				{#if relevantProviders.length === 0}
					<div class="text-[var(--sb-text-faint)] text-[12px]">This selection uses no providers — nothing to configure. Models build against the project target.</div>
				{:else}
					<div class="flex flex-col gap-4">
						{#each relevantProviders as p (p)}
							<div class="rounded-[2px] border border-[var(--border-subtle)] p-3">
								<div class="mb-2 flex items-center gap-2 text-[12px]"><span class="bg-[var(--sb-secondary)] h-[8px] w-[8px] rounded-[2px]"></span>{p}</div>
								{#if cfgValues[p]}
									<ConfigForm
										schema={providerSchema[p] ?? []}
										bind:values={cfgValues[p]}
										baseline={Object.fromEntries((providerSchema[p] ?? []).map((f) => [f.key, f.default]))}
									/>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- right: flag cheatsheet for the current verb -->
			<div class="sb-scroll overflow-auto px-5 py-4">
				<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Flags · {verb}</div>
				<div class="flex flex-col gap-1">
					{#each flagsByVerb[verb] as f (f.flag)}
						<button
							class="hover:bg-[var(--sb-hover)] flex items-baseline gap-2 rounded-[2px] px-2 py-1 text-left"
							onclick={() => {
								cmd = (cmd.trim() + ' ' + f.flag).trim() + ' ';
								userEdited = true;
								cmdEl?.focus();
							}}
						>
							<code class="text-primary text-[11.5px]">{f.flag}</code>
							<span class="text-[var(--sb-text-faint)] truncate text-[10.5px]">{f.desc}</span>
						</button>
					{/each}
				</div>
				<div class="text-[var(--sb-text-faint)] mt-4 text-[10.5px] leading-relaxed">
					Type <code class="text-foreground">--</code> for flags, or a name / <code class="text-foreground">tag:</code> / <code class="text-foreground">group:</code> for selection. The command below is the source of truth.
				</div>
			</div>
		</div>

		<!-- footer: smart command line -->
		<div class="relative border-t border-border px-6 py-3.5">
			{#if acOpen && suggestions.length}
				<div class="bg-popover absolute bottom-full left-6 z-50 mb-1 max-h-[240px] w-[480px] overflow-auto rounded-[2px] border border-border py-1" style="box-shadow:var(--sb-elev)">
					{#each suggestions as s, i (s.value)}
						<button
							class="flex w-full items-baseline gap-2 px-3 py-1.5 text-left {i === acIndex ? 'bg-[var(--sb-hover)]' : ''}"
							onmouseenter={() => (acIndex = i)}
							onclick={() => applySuggestion(s.value)}
						>
							<code class="text-foreground text-[12px]">{s.label}</code>
							<span class="text-[var(--sb-text-faint)] truncate text-[10.5px]">{s.hint}</span>
						</button>
					{/each}
				</div>
			{/if}
			<div class="flex items-center gap-3">
				<span class="text-[var(--sb-text-faint)] text-[12px]">$</span>
				<input
					bind:this={cmdEl}
					bind:value={cmd}
					oninput={() => {
						userEdited = true;
						refreshToken();
					}}
					onkeydown={onKeydown}
					onclick={refreshToken}
					onblur={() => setTimeout(() => (acOpen = false), 120)}
					spellcheck="false"
					class="text-foreground flex-1 bg-transparent text-[12.5px] outline-none"
					placeholder="sqb build --select +fact_orders --target snowflake_prod"
				/>
				<button class="bg-primary rounded-[2px] px-4 py-1.5 text-[13px] font-medium text-white disabled:opacity-50" disabled={cfgErrors > 0} onclick={run}>▷ Run</button>
			</div>
			{#if overrideArgs.length}
				<div class="text-[var(--sb-text-faint)] mt-1.5 pl-5 text-[12px]">+ overrides: {overrideArgs.join(' ')}</div>
			{/if}
			{#if cfgErrors > 0}<div class="text-[var(--sb-error)] mt-1.5 pl-5 text-[11px]">Fix {cfgErrors} config field{cfgErrors > 1 ? 's' : ''} to run</div>{/if}
		</div>
	</div>
{/if}

<style>
	.sb-scroll {
		scrollbar-width: thin;
		scrollbar-color: var(--border-strong) transparent;
	}
	.sb-scroll::-webkit-scrollbar {
		width: 9px;
		height: 9px;
	}
	.sb-scroll::-webkit-scrollbar-thumb {
		background: var(--border-strong);
		border-radius: 2px;
		border: 2px solid transparent;
		background-clip: content-box;
	}
</style>
