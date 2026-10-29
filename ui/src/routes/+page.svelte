<script lang="ts">
	import ActivityIcon from '@lucide/svelte/icons/activity';
	import AlertCircleIcon from '@lucide/svelte/icons/circle-alert';
	import HistoryIcon from '@lucide/svelte/icons/history';
	import BracesIcon from '@lucide/svelte/icons/braces';
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import RocketIcon from '@lucide/svelte/icons/rocket';
	import PlusIcon from '@lucide/svelte/icons/plus';
	import ColumnsIcon from '@lucide/svelte/icons/columns-3';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import RunTimeline from '$lib/components/timeline/run-timeline.svelte';
	import type { AttentionTone, ChangeKind } from '$lib/api';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import { formatAgo } from '$lib/format/time';
	import { runStatusLabel } from '$lib/status';

	const overview = createResource((client, scope) => client.overview(scope), ['runs', 'checks', 'node_status']);
	const data = $derived(overview.data ?? null);

	const attentionIcon: Record<AttentionTone, typeof AlertCircleIcon> = {
		error: AlertCircleIcon,
		stale: HistoryIcon,
		warning: TriangleAlertIcon
	};
	const issues = $derived(data?.attention ?? []);
	const healthTone = $derived(
		issues.some((i) => i.tone === 'error')
			? 'var(--sb-error)'
			: issues.some((i) => i.tone === 'warning')
				? 'var(--sb-warning)'
				: 'var(--sb-success)'
	);
	const latest = $derived(data?.latestRun ?? null);
	const latestText = $derived(
		latest ? `Last run ${runStatusLabel[latest.status].toLowerCase()} ${formatAgo(latest.endedAt, app.now)}` : 'No runs yet'
	);

	const changeIcon: Record<ChangeKind, typeof RocketIcon> = {
		snapshot: RocketIcon,
		macro: BracesIcon,
		model_added: PlusIcon,
		column_added: ColumnsIcon
	};
</script>

<AppTopbar title="Overview">
	<Button variant="outline" size="sm" onclick={() => overview.refresh()}>↻ Refresh</Button>
</AppTopbar>

<div class="min-h-0 flex-1 overflow-y-auto px-5 pb-16 pt-[18px]">
	<div class="flex flex-col gap-[14px]">
		<section class="health" style:--tone={healthTone}>
			<div class="health-head">
				<div class="health-icon">
					{#if issues.length}<AlertCircleIcon size={15} />{:else}<ActivityIcon size={15} />{/if}
				</div>
				<div class="health-copy">
					<strong>{issues.length ? `${app.targetName} needs attention` : `${app.targetName} is healthy`}</strong>
					<span>{issues.length ? `${issues.length} issues · ${latestText}` : latestText}</span>
				</div>
				<div class="health-facts">
					{#if data}
						<span><i class="status-dot success"></i><b>{data.currentNodes}</b> current</span>
						{#if data.staleNodes}<span><i class="status-dot stale"></i><b>{data.staleNodes}</b> stale</span>{/if}
						{#if data.failingChecks}<span><i class="status-dot error"></i><b>{data.failingChecks}</b> failed {data.failingChecks === 1 ? 'check' : 'checks'}</span>{/if}
					{/if}
				</div>
				{#if latest}<a href="/runs/{latest.id}">View latest run →</a>{/if}
			</div>
			{#if issues.length}
				<div class="issues">
					{#each issues as item (item.id)}
						{@const Glyph = attentionIcon[item.tone]}
						<a class="issue" href={item.href}>
							<span class="issue-icon {item.tone}"><Glyph size={14} /></span>
							<strong>{item.title}</strong>
							<span class="issue-detail">{item.detail}</span>
							<small>{item.since}</small>
							<b>{item.action} →</b>
						</a>
					{/each}
				</div>
			{/if}
		</section>

		<section class="metric-strip">
			{#each data?.metrics ?? [] as stat (stat.label)}
				<div class="metric">
					<span class="metric-label">{stat.label}</span>
					<div><strong class:stale-value={stat.tone === 'stale'}>{stat.value}</strong><small>{stat.detail}</small></div>
					<span class:success-note={stat.tone === 'success'} class:warning-note={stat.tone === 'warning'}>{stat.note}</span>
				</div>
			{/each}
		</section>



			<section class="surface-panel flex min-w-0 flex-col">
				<div class="panel-heading">
					<div><h2>Activity</h2><span>Runs and scheduled ticks by job</span></div>
					<a href="/runs?view=timeline">Open full timeline →</a>
				</div>
				<RunTimeline scroll={false} stickyTop={0} />
			</section>

		<div class="lower-grid">
		<section class="surface-panel freshness-panel">
			<div class="panel-heading">
				<div><h2>Warehouse freshness</h2><span>42 models · {app.targetName}</span></div>
				<a href="/catalog">Open catalog →</a>
			</div>
			<div class="freshness-body">
				<div class="freshness-bar"><i class="fresh"></i><i class="stale-segment"></i><i class="warn-segment"></i><i class="fail-segment"></i></div>
				<div class="freshness-legend">
					<span><i class="status-dot success"></i><b>33</b> fresh</span>
					<span><i class="status-dot stale"></i><b>3</b> stale</span>
					<span><i class="status-dot warning"></i><b>4</b> warning</span>
					<span><i class="status-dot error"></i><b>2</b> failed</span>
				</div>
				<div class="layers">
					{#each [['Staging', 12, 12], ['Intermediate', 9, 10], ['Marts', 12, 14], ['Sources', 5, 6]] as [layer, fresh, total] (layer)}
						<div class="layer-row">
							<span>{layer}</span>
							<div class="layer-bar"><i style:width="{(Number(fresh) / Number(total)) * 100}%"></i></div>
							<b>{fresh}/{total}</b>
						</div>
					{/each}
				</div>
			</div>
		</section>
		<section class="surface-panel changes-panel">
			<div class="panel-heading">
				<div><h2>Recent changes</h2><span>Snapshots and definition changes</span></div>
				<a href="/changes">All changes →</a>
			</div>
			<div>
				{#each data?.recentChanges ?? [] as c (c.id)}
					{@const Glyph = changeIcon[c.kind]}
					<a class="change" href={c.href}>
						<span class="change-icon {c.kind}"><Glyph size={14} /></span>
						<span class="change-copy"><strong>{c.title}</strong><span>{c.detail}</span></span>
						<small>{c.actor.name} · {formatAgo(c.at, app.now)}</small>
					</a>
				{/each}
			</div>
		</section>
		</div>

	</div>
</div>


<style>
	.health, .metric-strip, .surface-panel { box-shadow: var(--panel-shadow); border: 1px solid var(--panel-border); border-radius: 2px; background: var(--card); }
	.health { overflow: hidden; border-color: color-mix(in srgb, var(--tone) 30%, var(--border)); border-left: 3px solid var(--tone); }
	.health-head { display: flex; min-height: 49px; align-items: center; padding: 8px 13px; }
	.issues { border-top: 1px solid color-mix(in srgb, var(--tone) 18%, var(--border)); }
	.issue { display: grid; grid-template-columns: 22px auto minmax(0, 1fr) auto auto; align-items: center; gap: 10px; min-height: 38px; padding: 0 14px 0 17px; border-top: 1px solid var(--inner-line); font-size: 12.5px; }
	.issue:first-child { border-top: 0; }
	.issue:hover { background: var(--sb-hover); }
	.issue strong { font-weight: 600; white-space: nowrap; }
	.issue-detail { overflow: hidden; color: var(--muted-foreground); text-overflow: ellipsis; white-space: nowrap; }
	.issue small { color: var(--sb-text-faint); font-size: 12px; white-space: nowrap; }
	.issue b { min-width: 92px; color: var(--primary); font-weight: 500; text-align: right; white-space: nowrap; }
	.issue-icon { display: grid; width: 22px; height: 22px; place-items: center; border-radius: 2px; }
	.issue-icon.error { color: var(--sb-error); background: color-mix(in srgb, var(--sb-error) 12%, transparent); }
	.issue-icon.warning { color: var(--sb-warning); background: color-mix(in srgb, var(--sb-warning) 12%, transparent); }
	.issue-icon.stale { color: var(--sb-stale); background: color-mix(in srgb, var(--sb-stale) 12%, transparent); }
	.change { display: grid; grid-template-columns: 26px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--inner-line); }
	.change:last-child { border-bottom: 0; }
	.change:hover { background: var(--sb-hover); }
	.change-icon { display: grid; width: 26px; height: 26px; place-items: center; border-radius: 2px; color: var(--muted-foreground); background: var(--sb-hover); }
	.change-icon.macro { color: var(--sb-warning); background: color-mix(in srgb, var(--sb-warning) 11%, transparent); }
	.change-icon.snapshot { color: var(--primary); background: color-mix(in srgb, var(--primary) 11%, transparent); }
	.change-copy { min-width: 0; }
	.change-copy strong, .change-copy span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.change-copy strong { font-size: 12.5px; font-weight: 600; }
	.change-copy span { margin-top: 2px; color: var(--muted-foreground); font-size: 12px; }
	.change small { color: var(--sb-text-faint); font-size: 12px; white-space: nowrap; }
	.health-icon { display: grid; width: 29px; height: 29px; place-items: center; border-radius: 2px; color: var(--tone); background: color-mix(in srgb, var(--tone) 12%, transparent); }
	.health-copy { margin-left: 11px; }
	.health-copy strong, .health-copy span { display: block; }
	.health-copy strong { font-size: 13px; }
	.health-copy span { margin-top: 2px; color: var(--muted-foreground); font-size: 12px; }
	.health-facts { display: flex; gap: 20px; margin-left: 44px; color: var(--muted-foreground); font: 12px var(--font-sans); }
	.health-facts span, .freshness-legend span { display: flex; align-items: center; gap: 6px; }
	.health-facts b { color: var(--foreground); font-weight: 500; }
	.health-head > a, .panel-heading > a { margin-left: auto; color: var(--primary); font: 500 12.5px var(--font-sans); }
	.metric-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; }
	.metric { min-width: 0; padding: 15px 16px 14px; border-right: 1px solid var(--border); }
	.metric:last-child { border-right: 0; }
	.metric-label { display: block; color: var(--muted-foreground); font: 500 12px var(--font-sans); }
	.metric > div { display: flex; align-items: baseline; gap: 8px; margin-top: 7px; }
	.metric strong { font: 600 24px/1 var(--font-sans); letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
	.metric small { color: var(--muted-foreground); font-size: 12px; }
	.metric > span:last-child { display: block; margin-top: 9px; color: var(--sb-text-faint); font: 12px var(--font-sans); }
	.metric .success-note { color: var(--sb-success); }
	.metric .warning-note { color: var(--sb-warning); }
	.stale-value { color: var(--sb-stale); }
	.lower-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 0.8fr); gap: 14px; align-items: stretch; }
	.panel-heading { display: flex; min-height: 53px; align-items: center; padding: 0 14px 0 16px; border-bottom: 1px solid var(--border); }
	.panel-heading > div:first-child { margin-right: auto; }
	.panel-heading h2 { margin: 0; font: 600 13.5px var(--font-sans); }
	.panel-heading h2 + span { display: block; margin-top: 2px; color: var(--muted-foreground); font-size: 12px; }
	.status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; }
	.success { background: var(--sb-success); }
	.warning { background: var(--sb-warning); }
	.error { background: var(--sb-error); }
	.stale { background: var(--sb-stale); }
	.freshness-body { padding: 14px 16px 15px; }
	.freshness-bar { display: flex; height: 9px; overflow: hidden; border-radius: 2px; background: var(--sb-hover); }
	.freshness-bar i + i { border-left: 2px solid var(--card); }
	.freshness-bar .fresh { width: 78%; background: var(--sb-success); }
	.stale-segment { width: 8%; background: var(--sb-stale); }
	.warn-segment { width: 9%; background: var(--sb-warning); }
	.fail-segment { width: 5%; background: var(--sb-error); }
	.freshness-legend { display: flex; gap: 19px; margin-top: 11px; color: var(--muted-foreground); font: 12.5px var(--font-sans); }
	.freshness-legend b { color: var(--foreground); font-weight: 500; }
	.layers { display: flex; flex-direction: column; gap: 10px; margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border); }
	.layer-row { display: grid; grid-template-columns: 110px 1fr 48px; align-items: center; gap: 12px; font-size: 12.5px; }
	.layer-row > span { color: var(--muted-foreground); }
	.layer-row b { color: var(--foreground); font-weight: 500; text-align: right; font-variant-numeric: tabular-nums; }
	.layer-bar { height: 6px; overflow: hidden; border-radius: 2px; background: var(--sb-hover); }
	.layer-bar i { display: block; height: 100%; border-radius: 2px; background: var(--sb-success); }
	@media (max-width: 1250px) {
		.lower-grid { grid-template-columns: 1fr; }
		.health-facts span:nth-child(2) { display: none; }
		.metric { padding-right: 12px; padding-left: 12px; }
	}
</style>
