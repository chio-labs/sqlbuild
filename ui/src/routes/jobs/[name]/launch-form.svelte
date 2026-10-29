<script lang="ts">
	import { goto } from '$app/navigation';
	import type { JobDetail } from '$lib/api';
	import Button from '$lib/components/ui/button/button.svelte';
	import { app } from '$lib/state/app.svelte';

	let { job, onclose }: { job: JobDetail; onclose: () => void } = $props();

	let fullRefresh = $state(false);
	let useWindow = $state(false);
	let start = $state('');
	let end = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);

	const canRewrite = $derived(app.can('run.rewrite_history'));
	const rewrites = $derived(fullRefresh || useWindow);
	const placeholder = $derived(job.cursorType === 'integer' ? 'e.g. 1200' : 'e.g. 2026-10-01T00:00:00Z');
	const windowInvalid = $derived(
		useWindow &&
			(!start && !end
				? 'Give a start or an end'
				: job.cursorType === 'integer'
					? [start, end].some((v) => v && !/^\d+$/.test(v)) && 'Cursor values must be whole numbers'
					: [start, end].some((v) => v && Number.isNaN(Date.parse(v))) && 'Use ISO timestamps')
	);

	async function launch() {
		const scope = app.scope;
		if (!scope) return;
		busy = true;
		error = null;
		try {
			const run = await app.client.launchJob(scope, job.key, {
				fullRefresh: fullRefresh || undefined,
				window: useWindow && job.cursorType ? { type: job.cursorType, start: start || null, end: end || null } : undefined
			});
			onclose();
			await goto(`/runs/${run.id}`);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}
</script>

<div class="launch">
	<p class="title">Launch {job.kind === 'group' ? 'group' : 'job'} <code>{job.key}</code></p>
	<p class="faint">
		{job.kind === 'group' ? `A parent run with one child run per member (${job.members.length}).` : `${job.nodeCount} nodes, with the job's settings.`} It queues behind any run holding write claims on the same nodes.
	</p>
	<div class="opts" title={canRewrite ? undefined : 'Requires run.rewrite_history'}>
		<label class:off={!canRewrite}>
			<input type="checkbox" class="sb-check" bind:checked={fullRefresh} disabled={!canRewrite} />
			Full refresh <code>--full-refresh</code>
		</label>
		{#if job.cursorType}
			<label class:off={!canRewrite}>
				<input type="checkbox" class="sb-check" bind:checked={useWindow} disabled={!canRewrite} />
				Cursor window ({job.cursorType})
			</label>
			{#if useWindow}
				<div class="window">
					<input bind:value={start} {placeholder} aria-label="Window start" />
					<span class="faint">to</span>
					<input bind:value={end} {placeholder} aria-label="Window end" />
				</div>
				{#if windowInvalid}<p class="err">{windowInvalid}</p>{/if}
			{/if}
		{/if}
		{#if !canRewrite}<p class="faint">Full refresh and cursor windows require <code>run.rewrite_history</code>.</p>{:else if rewrites}<p class="warn">This run rewrites history: it is recorded with run.rewrite_history.</p>{/if}
	</div>
	{#if error}<p class="err">{error}</p>{/if}
	<div class="row">
		<Button size="sm" onclick={launch} disabled={busy || !!windowInvalid}>▷ Launch</Button>
		<Button size="sm" variant="ghost" onclick={onclose}>Cancel</Button>
	</div>
</div>

<style>
	.launch {
		position: absolute;
		top: calc(100% + 6px);
		right: 0;
		z-index: 60;
		width: 380px;
		padding: 12px 14px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--popover);
		box-shadow: var(--sb-elev);
		font-size: 12.5px;
	}
	.title {
		margin-bottom: 4px;
		font-weight: 600;
	}
	.faint {
		color: var(--muted-foreground);
		font-size: 12px;
	}
	.opts {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin: 10px 0;
	}
	label {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	label.off {
		opacity: 0.55;
	}
	code {
		font-family: var(--font-mono);
		font-size: 11.5px;
	}
	.window {
		display: flex;
		align-items: center;
		gap: 6px;
		padding-left: 22px;
	}
	.window input {
		width: 150px;
		padding: 3px 6px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--background);
		font-family: var(--font-mono);
		font-size: 11.5px;
	}
	.err {
		color: var(--sb-error);
		font-size: 12px;
	}
	.warn {
		color: var(--sb-warning);
		font-size: 12px;
	}
	.row {
		display: flex;
		gap: 6px;
	}
</style>
