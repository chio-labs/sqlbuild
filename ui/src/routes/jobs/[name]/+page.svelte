<script lang="ts">
	import { page } from '$app/state';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';

	const name = $derived(page.params.name ?? 'nightly_build');

	// mock job definition (would come from the API)
	const def = $derived({
		select: '+',
		desc: 'Full project build — every model, sources to marts.',
		schedule: 'daily 02:00 UTC',
		environment: 'prod',
		threads: 4,
		onFailure: 'block promotion',
		owner: '@analytics'
	});

	// triggers attached to this job (toggleable inline, like the Triggers page)
	type Trig = { name: string; type: 'schedule' | 'sensor'; cadence: string; enabled: boolean };
	let jobTriggers = $state<Trig[]>([
		{ name: 'nightly_build · daily', type: 'schedule', cadence: 'at 02:00 UTC', enabled: true },
		{ name: 'on_raw_orders_landed', type: 'sensor', cadence: 'when raw__orders has new data', enabled: false }
	]);
	function toggleTrig(name: string) {
		jobTriggers = jobTriggers.map((t) => (t.name === name ? { ...t, enabled: !t.enabled } : t));
	}

	type NodeStatus = 'ok' | 'fail' | 'warn' | 'stale' | 'src';
	const resolved: { name: string; kind: string; status: NodeStatus }[] = [
		{ name: 'raw__customers', kind: 'source', status: 'src' },
		{ name: 'raw__orders', kind: 'source', status: 'src' },
		{ name: 'raw__payments', kind: 'source', status: 'src' },
		{ name: 'stg_customers', kind: 'view', status: 'ok' },
		{ name: 'stg_orders', kind: 'view', status: 'ok' },
		{ name: 'stg_payments', kind: 'view', status: 'warn' },
		{ name: 'fact_orders', kind: 'table', status: 'ok' },
		{ name: 'dim_customers', kind: 'table', status: 'ok' },
		{ name: 'daily_revenue', kind: 'table', status: 'ok' },
		{ name: 'customer_status', kind: 'incremental', status: 'stale' },
		{ name: 'hourly_order_act', kind: 'incremental', status: 'ok' },
		{ name: 'hourly_activity_ctx', kind: 'incremental', status: 'fail' }
	];
	const statusColor: Record<NodeStatus, string> = {
		ok: 'var(--sb-success)',
		fail: 'var(--sb-error)',
		warn: 'var(--sb-warning)',
		stale: 'var(--sb-stale)',
		src: 'var(--sb-text-faint)'
	};
	function kindColor(kind: string): string {
		if (kind.startsWith('source') || kind.startsWith('seed') || kind.startsWith('loader')) return '#7c8aa5';
		if (kind === 'view') return '#5aa9e6';
		if (kind === 'table') return '#2e90ff';
		return '#3fb6c9';
	}

	type MiniRun = { id: string; status: 'ok' | 'fail' | 'warn'; when: string; dur: string; by: string; nodes: string };
	const runs: MiniRun[] = [
		{ id: 'run-9d21', status: 'fail', when: '2026-05-31 11:46', dur: '1.4s', by: '@scheduler', nodes: '8 ok · 1 warn · 1 fail · 3 skip' },
		{ id: 'run-2b70', status: 'ok', when: '2026-05-31 09:00', dur: '1.1s', by: '@scheduler', nodes: '12 ok' },
		{ id: 'run-1a05', status: 'warn', when: '2026-05-31 08:00', dur: '1.2s', by: '@scheduler', nodes: '11 ok · 1 warn' },
		{ id: 'run-77b3', status: 'ok', when: '2026-05-31 06:00', dur: '2.1s', by: '@scheduler', nodes: '12 ok' }
	];
	const runStatusColor: Record<string, string> = { ok: 'var(--sb-success)', fail: 'var(--sb-error)', warn: 'var(--sb-warning)' };
</script>

<AppTopbar title="Jobs">
	<Button variant="outline" size="sm">↻ Rerun last</Button>
	<Button size="sm">▷ Execute</Button>
</AppTopbar>

<div class="flex min-h-0 flex-1 flex-col">
	<!-- header -->
	<div class="flex items-center gap-3 border-b border-border px-6 py-3.5">
		<a href="/jobs" class="text-muted-foreground hover:text-foreground text-[13px]">← Jobs</a>
		<span class="font-display text-[17px] font-semibold">{name}</span>
		<code class="bg-secondary rounded-[2px] px-1.5 py-0.5 font-mono text-[11px]" style="color:var(--syn-keyword)">--select {def.select}</code>
		<span class="text-muted-foreground text-[12px]">· {resolved.length} nodes · {def.schedule}</span>
	</div>

	<div class="sb-scroll flex min-h-0 flex-1">
		<!-- main -->
		<div class="sb-scroll min-h-0 flex-1 overflow-auto p-6">
			<p class="text-muted-foreground mb-6 max-w-[760px] text-[13px] leading-relaxed">{def.desc}</p>

			<!-- recent runs -->
			<div class="mb-7">
				<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Recent runs</div>
				<table class="w-full border-collapse">
					<tbody>
						{#each runs as r (r.id)}
							<tr class="hover:bg-[var(--sb-hover)] cursor-pointer border-b border-[var(--border-subtle)]" onclick={() => (window.location.href = `/runs/${r.id}`)}>
								<td class="py-2.5 pr-3"><span class="inline-block h-1.5 w-1.5 rounded-[2px]" style:background={runStatusColor[r.status]}></span></td>
								<td class="py-2.5 pr-4"><a href="/runs/{r.id}" class="hover:text-primary text-[12.5px]">{r.id}</a></td>
								<td class="text-muted-foreground py-2.5 pr-4 text-[11.5px]">{r.nodes}</td>
								<td class="text-[var(--sb-text-faint)] py-2.5 pr-4 text-[11.5px]">{r.dur}</td>
								<td class="text-[var(--sb-text-faint)] py-2.5 pr-4 text-[11.5px]">{r.when}</td>
								<td class="text-muted-foreground py-2.5 text-[11.5px]">{r.by}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<!-- resolved nodes -->
			<div>
				<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Selected nodes · {resolved.length}</div>
				<div class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-1.5">
					{#each resolved as n (n.name)}
						<a href="/catalog/{n.name}" class="bg-secondary hover:bg-[var(--sb-hover)] flex items-center gap-2 rounded-[2px] border border-border px-2.5 py-1.5">
							<span class="h-[9px] w-[9px] shrink-0 rounded-[2px]" style:background={kindColor(n.kind)}></span>
							<span class="truncate text-[12px]">{n.name}</span>
							<span class="h-1.5 w-1.5 shrink-0 rounded-[2px]" style:background={statusColor[n.status]} title={n.status}></span>
						</a>
					{/each}
				</div>
			</div>
		</div>

		<!-- right: definition rail -->
		<div class="sb-scroll w-[280px] shrink-0 overflow-auto border-l border-border p-5">
			<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Definition</div>
			<div class="flex flex-col gap-2 text-[12.5px]">
				{#each [['Selector', def.select], ['Schedule', def.schedule], ['Environment', def.environment], ['Threads', String(def.threads)], ['On failure', def.onFailure], ['Owner', def.owner]] as [k, v] (k)}
					<div class="flex items-baseline justify-between gap-3">
						<span class="text-muted-foreground shrink-0">{k}</span>
						<span class="truncate text-right text-[11.5px]" title={v}>{v}</span>
					</div>
				{/each}
			</div>
			<div class="mt-5">
				<div class="text-[var(--sb-text-faint)] mb-1.5 flex items-center justify-between text-[12px] font-medium">
					<span>Triggers · {jobTriggers.length}</span>
					<a href="/triggers" class="text-[var(--sb-text-faint)] hover:text-primary normal-case tracking-normal">all →</a>
				</div>
				{#if jobTriggers.length === 0}
					<div class="text-[var(--sb-text-faint)] text-[11.5px]">No trigger — run manually.</div>
				{:else}
					<div class="flex flex-col gap-1.5">
						{#each jobTriggers as t (t.name)}
							<div class="flex items-center gap-2 rounded-[2px] border border-[var(--border-subtle)] px-2.5 py-2" style:opacity={t.enabled ? 1 : 0.6}>
								<span class="text-[var(--sb-text-faint)] shrink-0 text-[11px]">{t.type === 'schedule' ? '◷' : '⚡'}</span>
								<div class="min-w-0">
									<div class="truncate text-[11.5px]">{t.name}</div>
									<div class="text-[var(--sb-text-faint)] truncate text-[11.5px]">{t.cadence}</div>
								</div>
								<button
									class="relative ml-auto h-[16px] w-[28px] shrink-0 rounded-full transition-colors"
									style:background={t.enabled ? 'var(--sb-success)' : 'var(--border-strong)'}
									onclick={() => toggleTrig(t.name)}
									title={t.enabled ? 'Pause' : 'Enable'}
									aria-label="Toggle {t.name}"
								>
									<span class="absolute top-[2px] h-[12px] w-[12px] rounded-full bg-white transition-all" style:left={t.enabled ? '14px' : '2px'}></span>
								</button>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</div>
</div>

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
