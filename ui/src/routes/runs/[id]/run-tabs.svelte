<script lang="ts">
	import SearchIcon from '@lucide/svelte/icons/search';
	import type { RunDetail, RunEvent, RunEventLevel, RunOutputLine, RunStatement } from '$lib/api';
	import { highlightLines } from '$lib/sql/outline';
	import { formatStamp } from '$lib/format/time';
	import { app } from '$lib/state/app.svelte';
	import { clockTime, eventTone, formatCost } from '$lib/operate/labels';

	type Tab = 'events' | 'output' | 'statements' | 'provenance';

	let {
		detail,
		events,
		output,
		statements,
		tab = $bindable('events'),
		query = $bindable('')
	}: {
		detail: RunDetail;
		events: RunEvent[];
		output: RunOutputLine[];
		statements: RunStatement[];
		tab?: Tab;
		query?: string;
	} = $props();

	const LEVELS: RunEventLevel[] = ['debug', 'info', 'warn', 'error'];
	let levels = $state<Set<RunEventLevel>>(new Set(['info', 'warn', 'error']));
	let producer = $state<'all' | 'sqb' | 'scheduler'>('all');
	let stream = $state<'all' | 'stdout' | 'stderr'>('all');
	let statementId = $state<string | null>(null);

	const grouped = $derived(detail.children.length > 0);
	const q = $derived(query.trim().toLowerCase());
	const shownEvents = $derived(
		events.filter(
			(e) =>
				levels.has(e.level) &&
				(producer === 'all' || e.producer === producer) &&
				(!q || `${e.nodeKey ?? ''} ${e.type} ${e.message} ${e.runId}`.toLowerCase().includes(q))
		)
	);
	const levelCounts = $derived(Object.fromEntries(LEVELS.map((l) => [l, events.filter((e) => e.level === l).length])) as Record<RunEventLevel, number>);
	const shownOutput = $derived(output.filter((l) => (stream === 'all' || l.stream === stream) && (!q || l.text.toLowerCase().includes(q))));
	const shownStatements = $derived(statements.filter((s) => !q || `${s.nodeKey} ${s.kind}`.toLowerCase().includes(q)));
	const statement = $derived(shownStatements.find((s) => s.id === statementId) ?? shownStatements[0] ?? null);

	function toggleLevel(l: RunEventLevel) {
		const next = new Set(levels);
		if (next.has(l)) next.delete(l);
		else next.add(l);
		levels = next;
	}

	export function focusLevel(level: RunEventLevel) {
		tab = 'events';
		query = '';
		levels = levels.size === 1 && levels.has(level) ? new Set(['info', 'warn', 'error']) : new Set([level]);
	}

	const p = $derived(detail.provenance);
</script>

<div class="tabs">
	{#each [['events', `Events · ${events.length}`], ['output', 'Output'], ['statements', `Statements · ${statements.length}`], ['provenance', 'Provenance']] as [t, label] (t)}
		<button class:on={tab === t} onclick={() => (tab = t as Tab)}>{label}</button>
	{/each}
	{#if tab !== 'provenance'}
		<label class="search">
			<SearchIcon size={13} />
			<input bind:value={query} placeholder={tab === 'events' ? 'Filter nodes, events…' : tab === 'output' ? 'Filter output…' : 'Filter nodes…'} />
			{#if query}<button onclick={() => (query = '')} aria-label="Clear">✕</button>{/if}
		</label>
	{/if}
	{#if tab === 'events'}
		<div class="chips">
			{#each LEVELS as l (l)}
				<button class:on={levels.has(l)} onclick={() => toggleLevel(l)}>{l} <span>{levelCounts[l]}</span></button>
			{/each}
		</div>
		<div class="chips">
			{#each [['all', 'All producers'], ['sqb', 'sqb'], ['scheduler', 'Scheduler']] as [v, label] (v)}
				<button class:on={producer === v} onclick={() => (producer = v as typeof producer)}>{label}</button>
			{/each}
		</div>
	{:else if tab === 'output'}
		<div class="chips">
			{#each ['all', 'stdout', 'stderr'] as v (v)}
				<button class:on={stream === v} onclick={() => (stream = v as typeof stream)}>{v}</button>
			{/each}
		</div>
	{/if}
</div>

<div class="sb-scroll body">
	{#if tab === 'events'}
		<table class="events">
			<thead>
				<tr>
					<th>Time</th>
					{#if grouped}<th>Run</th>{/if}
					<th>Node</th>
					<th>Event</th>
					<th>Message</th>
				</tr>
			</thead>
			<tbody>
				{#each shownEvents as ev (ev.id)}
					<tr>
						<td class="faint nowrap" title={formatStamp(ev.occurredAt)}>{clockTime(ev.occurredAt)}</td>
						{#if grouped}<td class="mono faint"><a href="/runs/{ev.runId}">{ev.runId}</a></td>{/if}
						<td class="mono">{ev.nodeKey ?? '—'}</td>
						<td>
							<span class="type" style:--c={eventTone(ev)} title={ev.producer === 'scheduler' ? 'Scheduler fact' : 'Recall event'}>{ev.type}</span>
						</td>
						<td class="msg">{ev.message}</td>
					</tr>
				{:else}
					<tr><td colspan={grouped ? 5 : 4} class="empty">{events.length ? 'No events match the filter.' : 'No events yet.'}</td></tr>
				{/each}
			</tbody>
		</table>
	{:else if tab === 'output'}
		{#if shownOutput.length}
			<pre class="output">{#each shownOutput as line, i (i)}<span class:err={line.stream === 'stderr'}><span class="faint">{clockTime(line.at).slice(0, 8)}</span>  {line.text}
</span>{/each}</pre>
		{:else}
			<div class="empty">{output.length ? 'No output matches the filter.' : 'No output recorded for this run.'}</div>
		{/if}
	{:else if tab === 'statements'}
		{#if shownStatements.length}
			<div class="statements">
				<div class="st-list">
					{#each shownStatements as s (s.id)}
						<button class:on={statement?.id === s.id} onclick={() => (statementId = s.id)}>
							<i class={s.status}></i>
							<span class="mono">{s.nodeKey}</span>
							<span class="faint">{s.kind}</span>
							<span class="faint right">{s.rowsAffected != null ? `${s.rowsAffected.toLocaleString('en-GB')} rows` : s.status}</span>
						</button>
					{/each}
				</div>
				{#if statement}
					<div class="st-sql">
						<div class="st-head">
							<span class="mono">{statement.id}</span>
							<span class="faint">{statement.kind} · {statement.status} · invocation {statement.invocationId}</span>
						</div>
						{#if statement.error}<div class="st-error">{statement.error}</div>{/if}
						{#if app.can('view.sql')}
							<pre class="sql">{#each highlightLines(statement.sql, false) as line, i (i)}{@html line}
{/each}</pre>
						{:else}
							<div class="empty">Requires view.sql to show statement SQL.</div>
						{/if}
					</div>
				{/if}
			</div>
		{:else}
			<div class="empty">{statements.length ? 'No statements match the filter.' : 'No statements recorded for this run.'}</div>
		{/if}
	{:else}
		<div class="prov">
			<dl>
				<div><dt>Snapshot</dt><dd><code>{p.snapshotId}</code> · generation {p.snapshotGeneration}</dd></div>
				<div><dt>Git revision</dt><dd><code>{p.gitRevision}</code>{p.gitDirty ? ' (uncommitted changes)' : ''}</dd></div>
				<div><dt>Image</dt><dd><code title={p.imageId}>{p.imageId.slice(0, 19)}…</code></dd></div>
				<div><dt>sqb version</dt><dd>{p.sqbVersion}</dd></div>
				<div><dt>Selection</dt><dd><code>{p.selection.join(' ') || '(group)'}</code>{#if p.exclude.length} excluding <code>{p.exclude.join(' ')}</code>{/if}</dd></div>
				<div><dt>Command</dt><dd><code>{p.command}</code></dd></div>
				<div><dt>Rewrites history</dt><dd>{detail.run.rewriteHistory ? 'Yes (full refresh or explicit cursor window)' : 'No'}</dd></div>
				<div><dt>Priority</dt><dd>{detail.run.priority}</dd></div>
				<div><dt>Cost</dt><dd title={detail.run.cost?.source}>{detail.run.cost ? `${formatCost(detail.run.cost)} · ${detail.run.cost.source}` : '—'}</dd></div>
			</dl>
			<h4>Invocations and attempts</h4>
			{#if detail.invocations.length}
				<table class="events">
					<thead><tr><th>Invocation</th><th>Run</th><th>Attempt</th><th>Started</th><th>Ended</th><th>Exit code</th></tr></thead>
					<tbody>
						{#each detail.invocations as inv (inv.invocationId)}
							<tr>
								<td class="mono">{inv.invocationId}</td>
								<td class="mono"><a href="/runs/{inv.runId}">{inv.runId}</a></td>
								<td>{inv.attempt}</td>
								<td>{formatStamp(inv.startedAt)}</td>
								<td>{inv.endedAt ? formatStamp(inv.endedAt) : '—'}</td>
								<td>{inv.exitCode ?? '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{:else}
				<p class="faint">No invocation yet: the worker hasn't started.</p>
			{/if}
		</div>
	{/if}
</div>

<style>
	.tabs {
		display: flex;
		align-items: center;
		gap: 2px;
		padding: 0 16px;
		border-bottom: 1px solid var(--border);
	}
	.tabs > button {
		padding: 10px 12px;
		border-bottom: 2px solid transparent;
		color: var(--muted-foreground);
		font-size: 12px;
		font-weight: 500;
	}
	.tabs > button.on {
		border-color: var(--primary);
		color: var(--foreground);
	}
	.search {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-left: 12px;
		padding: 3px 8px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--secondary);
		color: var(--sb-text-faint);
	}
	.search input {
		width: 190px;
		border: 0;
		outline: 0;
		background: transparent;
		color: var(--foreground);
		font-size: 11.5px;
	}
	.chips {
		display: flex;
		gap: 2px;
		margin-left: 8px;
		padding: 2px;
		border-radius: 2px;
		background: var(--sb-hover);
	}
	.chips button {
		padding: 2px 8px;
		border-radius: 2px;
		color: var(--muted-foreground);
		font-size: 11.5px;
	}
	.chips button.on {
		background: var(--card);
		color: var(--foreground);
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
	}
	.chips span {
		color: var(--sb-text-faint);
	}
	.body {
		min-height: 0;
		flex: 1;
		overflow: auto;
	}
	.events {
		width: 100%;
		border-collapse: collapse;
		font-size: 12px;
	}
	.events th {
		position: sticky;
		top: 0;
		padding: 7px 16px;
		border-bottom: 1px solid var(--border);
		background: var(--background);
		color: var(--sb-text-faint);
		font-size: 11.5px;
		font-weight: 500;
		text-align: left;
	}
	.events td {
		padding: 6px 16px;
		border-bottom: 1px solid var(--border-subtle);
		vertical-align: top;
	}
	.events tr:hover td {
		background: var(--sb-hover);
	}
	.type {
		display: inline-flex;
		padding: 1px 7px;
		border-radius: 2px;
		background: color-mix(in srgb, var(--c) 13%, transparent);
		color: var(--c);
		font-family: var(--font-mono);
		font-size: 11px;
		white-space: nowrap;
	}
	.msg {
		color: var(--muted-foreground);
	}
	.mono,
	code {
		font-family: var(--font-mono);
		font-size: 11.5px;
	}
	.faint {
		color: var(--sb-text-faint);
	}
	.nowrap {
		white-space: nowrap;
	}
	.empty {
		padding: 32px;
		color: var(--sb-text-faint);
		font-size: 12px;
		text-align: center;
	}
	.output {
		padding: 12px 20px;
		color: var(--sb-mono);
		font-family: var(--font-mono);
		font-size: 11.5px;
		line-height: 1.7;
		white-space: pre-wrap;
	}
	.output .err {
		color: var(--sb-mono-err);
	}
	.statements {
		display: grid;
		height: 100%;
		grid-template-columns: minmax(280px, 380px) 1fr;
	}
	.st-list {
		overflow: auto;
		border-right: 1px solid var(--border);
	}
	.st-list button {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 8px;
		padding: 7px 14px;
		border-bottom: 1px solid var(--border-subtle);
		font-size: 12px;
		text-align: left;
	}
	.st-list button.on,
	.st-list button:hover {
		background: var(--sb-hover);
	}
	.st-list i {
		width: 7px;
		height: 7px;
		flex: 0 0 7px;
		border-radius: 50%;
		background: var(--sb-success);
	}
	.st-list i.failed {
		background: var(--sb-error);
	}
	.st-list i.running {
		background: var(--sb-running);
	}
	.st-list i.cancelled {
		background: var(--sb-text-faint);
	}
	.right {
		margin-left: auto;
	}
	.st-sql {
		overflow: auto;
	}
	.st-head {
		display: flex;
		gap: 12px;
		padding: 8px 16px;
		border-bottom: 1px solid var(--border-subtle);
		font-size: 12px;
	}
	.st-error {
		padding: 8px 16px;
		background: color-mix(in srgb, var(--sb-error) 8%, transparent);
		color: var(--sb-error);
		font-size: 12px;
	}
	.sql {
		padding: 12px 16px;
		font-family: var(--font-mono);
		font-size: 12px;
		line-height: 1.65;
		white-space: pre;
	}
	.prov {
		max-width: 920px;
		padding: 14px 20px;
		font-size: 12.5px;
	}
	.prov dl div {
		display: grid;
		grid-template-columns: 150px 1fr;
		padding: 4px 0;
	}
	.prov dt {
		color: var(--muted-foreground);
	}
	.prov h4 {
		margin: 16px 0 6px;
		color: var(--sb-text-faint);
		font-size: 12px;
		font-weight: 500;
	}
	.prov .events td,
	.prov .events th {
		padding-left: 0;
	}
	a:hover {
		color: var(--primary);
	}
	.sb-scroll {
		scrollbar-width: thin;
		scrollbar-color: var(--border-strong) transparent;
	}
</style>
