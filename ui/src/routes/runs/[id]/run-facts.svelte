<script lang="ts">
	import type { RunDetail } from '$lib/api';
	import { app } from '$lib/state/app.svelte';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { formatNodeCounts, runStatusLabel, runStatusTone } from '$lib/status';
	import { describeWait, formatSeconds, livenessLabel, livenessTone } from '$lib/operate/labels';

	let { detail }: { detail: RunDetail } = $props();

	const run = $derived(detail.run);
	const live = $derived(detail.liveness);
	const cancel = $derived(detail.cancel);
	const silent = $derived(live?.lastHeartbeatAt ? (app.now - Date.parse(live.lastHeartbeatAt)) / 1000 : null);
	const killDeadline = $derived(cancel?.sigtermAt ? Date.parse(cancel.sigtermAt) + cancel.graceSeconds * 1000 : null);

	type Step = { label: string; at: string | null; state: 'done' | 'active' | 'todo' | 'skipped'; note?: string };
	const cancelSteps = $derived.by((): Step[] => {
		if (!cancel) return [];
		const ended = !!cancel.terminatedAt;
		const notStarted = ended && !cancel.sigtermAt;
		return [
			{ label: 'cancel_requested', at: cancel.requestedAt, state: 'done', note: `by ${cancel.requestedBy.name}` },
			notStarted
				? { label: 'SIGTERM', at: null, state: 'skipped', note: 'not started; nothing to signal' }
				: { label: 'SIGTERM', at: cancel.sigtermAt, state: cancel.sigtermAt ? 'done' : 'active', note: cancel.sigtermAt ? 'statements cancelled' : 'sending' },
			cancel.sigkillAt
				? { label: 'SIGKILL', at: cancel.sigkillAt, state: 'done', note: `after ${cancel.graceSeconds}s grace` }
				: ended
					? { label: 'SIGKILL', at: null, state: 'skipped', note: cancel.exitCode != null ? `not needed: exited ${cancel.exitCode}` : 'not needed' }
					: {
							label: 'SIGKILL',
							at: null,
							state: cancel.sigtermAt ? 'active' : 'todo',
							note: killDeadline ? `in ${formatSeconds((killDeadline - app.now) / 1000)} if still running` : `${cancel.graceSeconds}s after SIGTERM`
						},
			{ label: 'terminated', at: cancel.terminatedAt, state: ended ? 'done' : 'todo', note: ended ? 'cancelled' : undefined }
		];
	});
</script>

<div class="facts">
	{#if detail.waits.length}
		<section class="card warn">
			<h4>Why it waits</h4>
			{#each detail.waits as w, i (i)}
				<p>
					{#each describeWait(w) as part, j (j)}{#if part.href}<a href={part.href} class:mono={part.code}>{part.text}</a>{:else if part.code}<code>{part.text}</code>{:else}{part.text}{/if}{/each}
				</p>
			{/each}
		</section>
	{/if}

	{#if cancel}
		<section class="card" class:warn={!cancel.terminatedAt}>
			<h4>Cancel</h4>
			<ol class="steps">
				{#each cancelSteps as step (step.label)}
					<li class={step.state}>
						<i></i>
						<span class="mono">{step.label}</span>
						{#if step.at}<span class="faint" title={formatStamp(step.at)}>{formatAgo(step.at, app.now)}</span>{/if}
						{#if step.note}<span class="faint">{step.note}</span>{/if}
					</li>
				{/each}
			</ol>
		</section>
	{/if}

	{#if live}
		<section class="card" class:bad={live.state === 'presumed_failed' || live.state === 'never_started'} class:warn={live.state === 'unresponsive'}>
			<h4>Liveness</h4>
			<p><i class="dot" style:background={livenessTone[live.state]}></i>{livenessLabel[live.state]}{#if live.exitCode != null} · exit code {live.exitCode}{/if}</p>
			{#if live.state === 'never_started'}
				<p class="faint">No start report within {live.startDeadlineSeconds}s of launch.</p>
			{:else if live.lastHeartbeatAt}
				<p class="faint">
					Last heartbeat {formatAgo(live.lastHeartbeatAt, app.now)}
					{#if live.state === 'unresponsive' && silent != null}
						· presumed failed in {formatSeconds(live.presumedFailedAfterSeconds - silent)}
					{:else if live.state === 'healthy'}
						· unresponsive after {live.unresponsiveAfterSeconds}s of silence
					{/if}
				</p>
			{/if}
			{#if live.workerInstance}<p class="faint mono">{live.workerInstance} · container {live.containerId}</p>{/if}
		</section>
	{/if}

	{#if detail.parent}
		<section class="card">
			<h4>Group</h4>
			<p>Child of <a class="mono" href="/runs/{detail.parent.id}">{detail.parent.id}</a> ({detail.parent.jobKey})</p>
			<p class="faint"><i class="dot" style:background={runStatusTone[detail.parent.status]}></i>{runStatusLabel[detail.parent.status]}</p>
		</section>
	{/if}

	{#if detail.children.length}
		<section class="card wide">
			<h4>Child runs · {detail.children.length}</h4>
			{#each detail.children as c (c.id)}
				<p class="child">
					<i class="dot" style:background={runStatusTone[c.status]}></i>
					<a class="mono" href="/runs/{c.id}">{c.id}</a>
					<span>{c.jobKey}</span>
					<span class="faint">{runStatusLabel[c.status]} · {formatNodeCounts(c.nodeCounts)}</span>
				</p>
			{/each}
		</section>
	{/if}

	<section class="card">
		<h4>Requested</h4>
		<p>{run.requestedBy.displayName} <span class="faint">({run.requestedBy.name})</span></p>
		{#if run.triggerId}
			<p class="faint">
				via <a href="/triggers/{run.triggerId}">{run.triggerName}</a>{#if run.tickScheduledFor} · tick due {formatStamp(run.tickScheduledFor)}{/if}
			</p>
		{/if}
		{#if run.runKey}<p class="faint">run key <code>{run.runKey}</code></p>{/if}
		{#if run.rerunOfRunId}<p class="faint">rerun of <a class="mono" href="/runs/{run.rerunOfRunId}">{run.rerunOfRunId}</a></p>{/if}
		<p class="faint">queued {formatStamp(run.queuedAt)}{#if run.launchedAt} · launched {formatStamp(run.launchedAt)}{/if}</p>
	</section>
</div>

<style>
	.facts {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		padding: 10px 24px;
		border-bottom: 1px solid var(--border);
	}
	.card {
		min-width: 220px;
		max-width: 420px;
		flex: 1 1 220px;
		padding: 8px 11px;
		border: 1px solid var(--border-subtle);
		border-radius: 2px;
		font-size: 12px;
	}
	.card.wide {
		max-width: 560px;
		flex-basis: 360px;
	}
	.card.warn {
		border-color: color-mix(in srgb, var(--sb-warning) 45%, transparent);
		background: color-mix(in srgb, var(--sb-warning) 5%, transparent);
	}
	.card.bad {
		border-color: color-mix(in srgb, var(--sb-error) 45%, transparent);
		background: color-mix(in srgb, var(--sb-error) 5%, transparent);
	}
	h4 {
		margin-bottom: 4px;
		color: var(--sb-text-faint);
		font-size: 11.5px;
		font-weight: 500;
	}
	p {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0 4px;
		line-height: 1.6;
	}
	p.child {
		gap: 8px;
	}
	.dot {
		display: inline-block;
		width: 7px;
		height: 7px;
		margin-right: 5px;
		border-radius: 50%;
	}
	.faint {
		color: var(--muted-foreground);
	}
	.mono,
	code {
		font-family: var(--font-mono);
		font-size: 11.5px;
	}
	a {
		color: var(--primary);
	}
	a:hover {
		text-decoration: underline;
	}
	.steps {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.steps li {
		display: flex;
		align-items: center;
		gap: 7px;
	}
	.steps i {
		width: 8px;
		height: 8px;
		border: 1.5px solid var(--sb-text-faint);
		border-radius: 50%;
	}
	.steps li.done i {
		border-color: var(--sb-success);
		background: var(--sb-success);
	}
	.steps li.active i {
		border-color: var(--sb-warning);
		animation: pulse 1.2s ease-in-out infinite;
	}
	.steps li.skipped {
		opacity: 0.6;
	}
	.steps li.skipped i {
		border-style: dashed;
	}
	@keyframes pulse {
		50% {
			background: var(--sb-warning);
		}
	}
</style>
