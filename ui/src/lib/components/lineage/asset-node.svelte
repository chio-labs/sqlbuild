<script lang="ts">
	import GitCompareIcon from '@lucide/svelte/icons/git-compare';
	import { Handle, Position, type NodeProps } from '@xyflow/svelte';
	import {
		Database,
		Table2,
		Eye,
		Layers,
		FunctionSquare,
		Sprout,
		Download,
		GitMerge,
		Repeat,
		Columns3,
		User,
		type Icon as IconType
	} from '@lucide/svelte';
	import { nodeFields } from '$lib/lineage/node-fields.svelte';

	type AssetData = {
		name: string;
		kind: string;
		status: 'ok' | 'fail' | 'warn' | 'stale' | 'run' | 'src';
		checks?: string;
		checksColor?: string;
		dimmed?: boolean;
		icon?: string;
		freshness?: string;
		description?: string;
		owner?: string;
		tags?: string[];
		columnCount?: number;
		drift?: 'direct' | 'compiled' | 'upstream';
	};

	let { data, selected }: NodeProps = $props();
	const d = $derived(data as AssetData);
	const f = $derived(nodeFields.value);

	const statusColor: Record<string, string> = {
		ok: 'var(--sb-success)',
		fail: 'var(--sb-error)',
		warn: 'var(--sb-warning)',
		stale: 'var(--sb-stale)',
		run: 'var(--sb-running)',
		src: 'var(--sb-text-faint)'
	};
	const statusLabel: Record<string, string> = {
		ok: 'Materialized',
		fail: 'Failed',
		warn: 'Warning',
		stale: 'Stale',
		run: 'Running',
		src: 'External source'
	};
	const icons: Record<string, typeof IconType> = {
		source: Database,
		loader: Download,
		seed: Sprout,
		view: Eye,
		table: Table2,
		merge: GitMerge,
		delete_insert: Repeat,
		microbatch: Layers,
		fn: FunctionSquare
	};
	const Glyph = $derived(icons[d.icon ?? ''] ?? Table2);
	const tone = $derived(statusColor[d.status]);
	const kindShort = $derived(d.kind.split(' · ')[0]);
	const when = $derived(d.status === 'src' ? '' : d.status === 'fail' ? '' : (d.freshness ?? ''));

	const hasDetail = $derived(
		!!(
			(f.description && d.description) ||
			(f.owner && d.owner) ||
			(f.tags && d.tags?.length) ||
			(f.columns && d.columnCount != null)
		)
	);
</script>

<div class="node" class:selected class:dimmed={d.dimmed}>
	<Handle type="target" position={Position.Left} class="node-handle" />

	<div class="head">
		<Glyph size={14} strokeWidth={1.75} class="glyph" />
		<span class="name" title={d.name}>{d.name}</span>
		{#if f.kind}<span class="kind">{kindShort}</span>{/if}
	</div>

	{#if hasDetail}
		<div class="detail">
			{#if f.description && d.description}<p>{d.description}</p>{/if}
			{#if f.owner && d.owner}<span><User size={11} /> {d.owner}</span>{/if}
			{#if f.columns && d.columnCount != null}<span><Columns3 size={11} /> {d.columnCount} columns</span>{/if}
			{#if f.tags && d.tags?.length}<span>{d.tags.join(', ')}</span>{/if}
		</div>
	{/if}

	{#if f.status || (f.checks && d.checks) || (f.freshness && when)}
		<div class="status" style:--tone={tone}>
			{#if f.status}
				<i></i>
				<span class="label">{statusLabel[d.status]}</span>
			{/if}
			{#if f.status && when}<span class="when">{when}</span>{/if}
			{#if d.drift}
				<span class="drift" class:upstream={d.drift === 'upstream'} title={d.drift === 'upstream' ? 'Stale because an upstream model changed since the last build' : 'Stale because this model’s SQL changed since the last build'}><GitCompareIcon size={10} strokeWidth={2} />{d.drift === 'upstream' ? 'upstream' : 'drift'}</span>
			{/if}
			{#if f.checks && d.checks}
				<span class="checks" style:color={d.checksColor ?? 'var(--muted-foreground)'}>{d.checks}</span>
			{/if}
		</div>
	{/if}

	<Handle type="source" position={Position.Right} class="node-handle" />
</div>

<style>
	.node {
		width: 236px;
		overflow: hidden;
		border: 1px solid var(--node-border);
		border-radius: 2px;
		background: var(--card);
		color: var(--foreground);
		font-family: var(--font-sans);
		transition:
			opacity 0.15s,
			border-color 0.15s;
	}
	.node:hover {
		border-color: color-mix(in srgb, var(--foreground) 35%, transparent);
	}
	.node.selected {
		border-color: var(--primary);
		box-shadow: 0 0 0 1px var(--primary);
	}
	.node.dimmed {
		opacity: 0.35;
	}
	.head {
		display: flex;
		height: 34px;
		align-items: center;
		gap: 8px;
		padding: 0 10px;
	}
	.head :global(.glyph) {
		flex: 0 0 auto;
		color: var(--muted-foreground);
	}
	.name {
		min-width: 0;
		flex: 1;
		overflow: hidden;
		font-size: 12.5px;
		font-weight: 600;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.kind {
		flex: 0 0 auto;
		color: var(--sb-text-faint);
		font-size: 11px;
	}
	/* drift is a cause of staleness, so it shares the stale colour */
	.drift {
		display: inline-flex;
		flex: 0 0 auto;
		align-items: center;
		gap: 3px;
		padding: 0 5px;
		border: 1px solid transparent;
		border-radius: 2px;
		background: color-mix(in srgb, var(--sb-stale) 16%, transparent);
		color: var(--sb-stale);
		font-size: 10.5px;
		font-weight: 600;
		line-height: 15px;
	}
	.drift.upstream {
		border: 1px dashed color-mix(in srgb, var(--sb-stale) 55%, transparent);
		background: transparent;
		font-weight: 500;
	}
	.detail {
		display: flex;
		flex-direction: column;
		gap: 3px;
		padding: 0 10px 8px 32px;
		color: var(--muted-foreground);
		font-size: 11px;
	}
	.detail p {
		margin: 0;
		line-height: 1.35;
	}
	.detail span {
		display: flex;
		align-items: center;
		gap: 5px;
	}
	.status {
		display: flex;
		height: 26px;
		align-items: center;
		gap: 6px;
		padding: 0 10px;
		border-top: 1px solid var(--border);
		background: color-mix(in srgb, var(--tone) 9%, var(--card));
		font-size: 11px;
	}
	.status i {
		width: 7px;
		height: 7px;
		flex: 0 0 7px;
		border-radius: 50%;
		background: var(--tone);
	}
	.label {
		color: var(--foreground);
		font-weight: 500;
	}
	.when {
		color: var(--muted-foreground);
	}
	.when::before {
		content: '·';
		margin-right: 6px;
		color: var(--sb-text-faint);
	}
	.checks {
		margin-left: auto;
		font-variant-numeric: tabular-nums;
	}
	.node :global(.node-handle) {
		width: 6px;
		height: 6px;
		min-width: 0;
		min-height: 0;
		border: 0;
		background: transparent;
	}
</style>
