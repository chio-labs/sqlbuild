<script lang="ts">
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import ChevronsUpDownIcon from '@lucide/svelte/icons/chevrons-up-down';
	import type { LocationHealth } from '$lib/api';
	import { app } from '$lib/state/app.svelte';

	const healthTone: Record<LocationHealth, string> = {
		healthy: 'var(--sb-success)',
		degraded: 'var(--sb-warning)',
		falling_back: 'var(--sb-warning)',
		broken: 'var(--sb-error)'
	};
	const healthLabel: Record<LocationHealth, string> = {
		healthy: 'Healthy',
		degraded: 'Degraded',
		falling_back: 'Falling back to last good image',
		broken: 'Broken'
	};

	const locations = $derived(app.bootstrap?.locations ?? []);
</script>

<div class="switchers">
	<DropdownMenu.Root>
		<DropdownMenu.Trigger class="switch" aria-label="Switch location">
			<span class="badge">{app.location?.name.slice(0, 1).toUpperCase() ?? '·'}</span>
			<span class="copy">
				<small>Location</small>
				<span class="value">{app.location?.name ?? '—'}</span>
			</span>
			{#if app.location && app.location.health !== 'healthy'}
				<i class="dot" style:background={healthTone[app.location.health]} title={healthLabel[app.location.health]}></i>
			{/if}
			<ChevronsUpDownIcon size={13} class="chev" />
		</DropdownMenu.Trigger>
		<DropdownMenu.Content class="w-60">
			<DropdownMenu.Label>Locations</DropdownMenu.Label>
			<DropdownMenu.RadioGroup value={app.locationId} onValueChange={(id) => app.selectLocation(id)}>
				{#each locations as location (location.id)}
					<DropdownMenu.RadioItem value={location.id}>
						<i class="dot" style:background={healthTone[location.health]}></i>
						<span class="flex min-w-0 flex-col">
							<span class="truncate">{location.name}</span>
							<small class="text-muted-foreground text-[11px]">{healthLabel[location.health]}</small>
						</span>
					</DropdownMenu.RadioItem>
				{/each}
			</DropdownMenu.RadioGroup>
		</DropdownMenu.Content>
	</DropdownMenu.Root>

	<DropdownMenu.Root>
		<DropdownMenu.Trigger class="switch" aria-label="Switch target">
			<span class="copy">
				<small>Target</small>
				<span class="value">{app.target?.name ?? '—'}<em>{app.target?.adapter ?? ''}</em></span>
			</span>
			<ChevronsUpDownIcon size={13} class="chev" />
		</DropdownMenu.Trigger>
		<DropdownMenu.Content class="w-60">
			<DropdownMenu.Label>Targets in {app.location?.name}</DropdownMenu.Label>
			<DropdownMenu.RadioGroup value={app.targetName} onValueChange={(name) => app.selectTarget(name)}>
				{#each app.location?.targets ?? [] as target (target.name)}
					<DropdownMenu.RadioItem value={target.name}>
						<span class="flex min-w-0 flex-col">
							<span class="truncate">{target.name}{target.isDefault ? ' · default' : ''}</span>
							<small class="text-muted-foreground text-[11px]">
								{target.adapter}{target.snapshot ? ` · generation ${target.snapshot.generation}` : ' · no snapshot'}
							</small>
						</span>
					</DropdownMenu.RadioItem>
				{/each}
			</DropdownMenu.RadioGroup>
		</DropdownMenu.Content>
	</DropdownMenu.Root>
</div>

<style>
	.switchers {
		display: flex;
		flex-direction: column;
		overflow: hidden;
		margin-bottom: 12px;
		border: 1px solid var(--sidebar-border);
		border-radius: 6px;
	}
	.switchers :global(.switch) {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 10px;
		padding: 7px 10px;
		text-align: left;
		font-size: 13px;
	}
	.switchers :global(.switch + .switch) {
		border-top: 1px solid var(--sidebar-border);
	}
	.switchers :global(.switch:hover),
	.switchers :global(.switch[data-state='open']) {
		background: var(--sb-hover);
	}
	.switchers :global(.chev) {
		margin-left: auto;
		flex-shrink: 0;
		color: var(--muted-foreground);
	}
	.badge {
		display: grid;
		width: 20px;
		height: 20px;
		flex-shrink: 0;
		place-items: center;
		border-radius: 2px;
		background: var(--secondary);
		color: var(--muted-foreground);
		font-size: 10px;
		font-weight: 600;
	}
	.copy {
		display: flex;
		min-width: 0;
		flex-direction: column;
		line-height: 1.2;
	}
	.copy small {
		color: var(--muted-foreground);
		font-size: 10.5px;
	}
	.value {
		overflow: hidden;
		font-weight: 500;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.value em {
		margin-left: 6px;
		color: var(--muted-foreground);
		font-size: 11px;
		font-style: normal;
		font-weight: 400;
	}
	.dot {
		display: inline-block;
		width: 7px;
		height: 7px;
		flex-shrink: 0;
		border-radius: 50%;
	}
</style>
