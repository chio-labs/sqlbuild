<script lang="ts">
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import type { TriggerState } from '$lib/api';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import CodePreview from '$lib/components/code/code-preview.svelte';
	import GatedButton from '$lib/components/operate/gated-button.svelte';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import { formatAgo, formatIn, formatStamp } from '$lib/format/time';
	import { runStatusLabel, runStatusTone } from '$lib/status';
	import { stateEventLabel, triggerKindLabel } from '$lib/operate/labels';
	import SensorPanel from './sensor-panel.svelte';
	import TickLog from './tick-log.svelte';

	let { id }: { id: string } = $props();

	const res = createResource((client, scope) => client.getTrigger(scope, id), ['triggers', 'ticks', 'runs']);
	const t = $derived(res.data ?? null);
	const isSchedule = $derived(t?.type === 'schedule');

	let reason = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function run(action: () => Promise<unknown>) {
		busy = true;
		error = null;
		try {
			await action();
			reason = '';
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}
	function setState(state: TriggerState) {
		const scope = app.scope;
		if (scope) void run(() => app.client.setTriggerStates(scope, [id], state, reason.trim() || null));
	}
	function resetDefault() {
		const scope = app.scope;
		if (scope) void run(() => app.client.resetTriggerToDefault(scope, id));
	}
</script>

<AppTopbar title="Triggers">
	{#if t}
		<input class="reason" bind:value={reason} placeholder="Reason (recorded)" aria-label="Reason for the change" />
		{#if t.state !== t.defaultState}
			<GatedButton requires="trigger.toggle" {busy} onclick={resetDefault}>Reset to code default ({t.defaultState})</GatedButton>
		{/if}
		{#if t.state === 'running'}
			<GatedButton requires="trigger.toggle" {busy} onclick={() => setState('paused')}>Pause</GatedButton>
		{:else}
			<GatedButton requires="trigger.toggle" variant="default" {busy} onclick={() => setState('running')}>Enable</GatedButton>
		{/if}
	{/if}
</AppTopbar>

<div class="flex min-h-0 flex-1 flex-col">
	<div class="head">
		<a href="/triggers" class="back">← Triggers</a>
		<span class="font-display text-[17px] font-semibold">{t?.name ?? id}</span>
		{#if t}
			<span class="sb-status" style:--tone={t.state === 'running' ? 'var(--sb-success)' : 'var(--sb-text-faint)'}><span></span>{t.state}</span>
			<span class="faint">{t.state === t.defaultState ? 'matches the code default' : `code default ${t.defaultState}`}</span>
			<span class="faint">· {triggerKindLabel[t.kind]} · {t.cadence}</span>
		{/if}
	</div>
	{#if res.error}<div class="msg err">Couldn't load this trigger: {res.error}</div>{:else if res.data === null}<div class="msg">No trigger <code>{id}</code> in this target's snapshot.</div>{/if}
	{#if error}<div class="msg err">{error}</div>{/if}

	{#if t}
		{#if t.warning || t.calendar?.low}
			<div class="warning"><TriangleAlertIcon size={14} /> {t.warning}</div>
		{/if}
		<div class="flex min-h-0 flex-1">
			<div class="main sb-scroll">
				{#if isSchedule}
					<section>
						<h3>Ticks · {t.ticks.length}</h3>
						<TickLog ticks={t.ticks} />
					</section>
				{:else}
					<SensorPanel trigger={t} />
				{/if}
				<section>
					<h3>Declaration <span>read-only; defined in code</span></h3>
					<CodePreview file="{t.declaration.sourceFile}:{t.declaration.line}" code={t.declaration.code} language="text" maxLines={20} />
				</section>
			</div>

			<aside class="rail sb-scroll">
				<h3>Definition</h3>
				<dl>
					<div><dt>Kind</dt><dd>{triggerKindLabel[t.kind]}</dd></div>
					<div><dt>Launches</dt><dd>{#if t.jobKey}<a href="/jobs/{t.jobKey}">{t.jobKey}</a>{:else}code action only{/if}</dd></div>
					{#if t.cron}<div><dt>Cron</dt><dd><code>{t.cron}</code></dd></div>{/if}
					{#if t.timezone}<div><dt>Time zone</dt><dd>{t.timezone}</dd></div>{/if}
					{#if t.catchUp}<div><dt>Catch-up</dt><dd>{t.catchUp.mode === 'latest' ? 'latest missed time' : `every missed time, up to ${t.catchUp.max}`}</dd></div>{/if}
					<div><dt>Targets</dt><dd>{t.targets?.join(', ') ?? 'all targets'}</dd></div>
					<div><dt>Code default</dt><dd>{t.defaultState}</dd></div>
					<div><dt>Source</dt><dd><code>{t.sourceFile}</code></dd></div>
				</dl>

				{#if isSchedule}
					<h3>Next due</h3>
					{#if t.state === 'paused'}
						<p class="faint">Paused: no ticks are evaluated. Enabling catches up per the catch-up policy.</p>
					{:else if t.upcoming.length}
						{#each t.upcoming as due, i (due)}
							<p class:faint={i > 0}>{formatStamp(due)} <span class="faint">{formatIn(due, app.now)}</span></p>
						{/each}
					{:else}
						<p class="faint">No upcoming times stored.</p>
					{/if}
				{/if}

				{#if t.calendar}
					<h3>Calendar horizon</h3>
					<dl>
						<div><dt>Computed ahead</dt><dd>{t.calendar.horizon}</dd></div>
						<div><dt>Stored until</dt><dd class:warn={t.calendar.low}>{formatStamp(t.calendar.storedUntil)}</dd></div>
						<div><dt>Last refreshed</dt><dd>{formatAgo(t.calendar.lastRefreshedAt, app.now)}</dd></div>
						<div><dt>Warns below</dt><dd>{t.calendar.lowHorizonWarningBelow}</dd></div>
					</dl>
					<p class="help">The calendar function runs in the code location on publish and on a refresh cadence; the scheduler ticks from the stored times.</p>
				{/if}

				<h3>Last run</h3>
				{#if t.lastRun}
					<p><i class="dot" style:background={runStatusTone[t.lastRun.status]}></i><a class="mono" href="/runs/{t.lastRun.id}">{t.lastRun.id}</a> <span class="faint">{runStatusLabel[t.lastRun.status]}{t.lastRun.startedAt ? ` · ${formatAgo(t.lastRun.startedAt, app.now)}` : ''}</span></p>
				{:else}
					<p class="faint">No runs yet.</p>
				{/if}

				<h3>State history</h3>
				{#if t.stateHistory.length}
					{#each t.stateHistory as e (e.id)}
						<div class="event">
							<div><b>{stateEventLabel[e.kind]}</b>{#if e.value} <code>{e.value}</code>{/if}</div>
							<div class="faint">{e.actor.displayName} ({e.actor.name}) · <span title={formatStamp(e.at)}>{formatAgo(e.at, app.now)}</span></div>
							{#if e.reason}<div class="faint">“{e.reason}”</div>{/if}
						</div>
					{/each}
				{:else}
					<p class="faint">No overrides: the state comes from code.</p>
				{/if}
			</aside>
		</div>
	{/if}
</div>

<style>
	.head {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 24px;
		border-bottom: 1px solid var(--border);
		font-size: 12.5px;
	}
	.back {
		color: var(--muted-foreground);
		font-size: 13px;
	}
	.reason {
		width: 200px;
		height: 32px;
		padding: 0 9px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--background);
		font-size: 12.5px;
	}
	.faint {
		color: var(--muted-foreground);
	}
	.msg {
		padding: 14px 24px;
		color: var(--muted-foreground);
		font-size: 13px;
	}
	.err {
		color: var(--sb-error);
	}
	.warning {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 24px;
		border-bottom: 1px solid color-mix(in srgb, var(--sb-warning) 40%, transparent);
		background: color-mix(in srgb, var(--sb-warning) 7%, transparent);
		color: var(--sb-warning);
		font-size: 12.5px;
	}
	.main {
		min-width: 0;
		flex: 1;
		overflow: auto;
		padding: 18px 24px;
	}
	section {
		margin-bottom: 24px;
	}
	h3 {
		display: flex;
		align-items: baseline;
		gap: 8px;
		margin: 18px 0 8px;
		color: var(--sb-text-faint);
		font-size: 12px;
		font-weight: 500;
	}
	h3 span {
		font-weight: 400;
	}
	section h3,
	.rail h3:first-child {
		margin-top: 0;
	}
	code,
	.mono {
		font-family: var(--font-mono);
		font-size: 11.5px;
	}
	.rail {
		width: 330px;
		flex-shrink: 0;
		overflow: auto;
		padding: 18px 20px;
		border-left: 1px solid var(--border);
		font-size: 12.5px;
	}
	dl div {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		padding: 3px 0;
	}
	dt {
		color: var(--muted-foreground);
	}
	dd {
		text-align: right;
	}
	dd.warn {
		color: var(--sb-warning);
	}
	p {
		padding: 2px 0;
	}
	.help {
		margin-top: 6px;
		color: var(--sb-text-faint);
		font-size: 11.5px;
		line-height: 1.5;
	}
	.dot {
		display: inline-block;
		width: 7px;
		height: 7px;
		margin-right: 6px;
		border-radius: 50%;
	}
	.event {
		padding: 6px 0;
		border-bottom: 1px solid var(--border-subtle);
	}
	a {
		color: var(--primary);
	}
	.sb-scroll {
		scrollbar-width: thin;
		scrollbar-color: var(--border-strong) transparent;
	}
</style>
