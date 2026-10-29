<script lang="ts">
	import { page } from '$app/state';
	import CheckCircleIcon from '@lucide/svelte/icons/circle-check';
	import ClockIcon from '@lucide/svelte/icons/clock-3';
	import DatabaseIcon from '@lucide/svelte/icons/database';
	import GitBranchIcon from '@lucide/svelte/icons/git-branch';
	import LayoutDashboardIcon from '@lucide/svelte/icons/layout-dashboard';
	import ListIcon from '@lucide/svelte/icons/list';
	import PlayIcon from '@lucide/svelte/icons/play';
	import SettingsIcon from '@lucide/svelte/icons/settings';
	import SlidersIcon from '@lucide/svelte/icons/sliders-horizontal';
	import type { Component } from 'svelte';

	type NavItem = { label: string; href: string; icon: Component };
	type NavGroup = { section: string; items: NavItem[] };

	const groups: NavGroup[] = [
		{
			section: 'Build',
			items: [
				{ label: 'Overview', href: '/', icon: LayoutDashboardIcon },
				{ label: 'Lineage', href: '/lineage', icon: GitBranchIcon },
				{ label: 'Catalog', href: '/catalog', icon: DatabaseIcon }
			]
		},
		{
			section: 'Operate',
			items: [
				{ label: 'Runs', href: '/runs', icon: ListIcon },
				{ label: 'Jobs', href: '/jobs', icon: PlayIcon },
				{ label: 'Triggers', href: '/triggers', icon: ClockIcon },
				{ label: 'Checks', href: '/checks', icon: CheckCircleIcon }
			]
		}
	];

	const footerItems: NavItem[] = [
		{ label: 'Providers', href: '/providers', icon: SlidersIcon },
		{ label: 'Settings', href: '/settings', icon: SettingsIcon }
	];

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname.startsWith(href);
	}
</script>

<aside class="app-sidebar bg-sidebar flex h-screen w-56 shrink-0 flex-col border-r border-[var(--sidebar-border)] px-3 py-4">
	<div class="flex items-center gap-2 px-2 pb-4">
		<img src="/logo.png" alt="SQLBuild" class="logo-dark h-6 w-auto" />
		<img src="/logo-light.png" alt="SQLBuild" class="logo-light h-6 w-auto" />
		<span class="text-muted-foreground ml-auto text-[11px]">v0.87</span>
	</div>

		<div class="project-row mb-3 flex items-center gap-2.5 rounded-md border border-[var(--sidebar-border)] px-2.5 py-2 text-[13px] font-medium">
		<span class="bg-secondary text-muted-foreground grid h-5 w-5 place-items-center rounded-[2px] text-[10px] font-semibold">W</span>
		<span class="flex flex-col leading-tight">waffle-shop<small class="text-muted-foreground text-[11px] font-normal">Snowflake · production</small></span>
		<span class="ml-auto text-[11px] text-[#626975]">⌄</span>
	</div>

	<nav class="flex flex-1 flex-col gap-px">
		{#each groups as group (group.section)}
			<div class="text-muted-foreground px-3 pb-1 pt-4 text-[11.5px] font-medium">
				{group.section}
			</div>
			{#each group.items as item (item.href)}
				{@const Glyph = item.icon}
				<a
					href={item.href}
					class="relative flex items-center gap-2.5 rounded-md px-3 py-[7px] text-[13px] {isActive(item.href)
						? 'bg-[var(--sidebar-accent)] text-foreground font-medium'
						: 'text-[var(--sidebar-foreground)] hover:bg-[var(--sb-hover)] hover:text-foreground'}"
				>
					<span class="grid w-4 place-items-center opacity-80"><Glyph size={15} /></span>
					{item.label}
					{#if item.href === '/catalog'}
						<span class="nav-count ml-auto text-[11.5px]">42</span>
					{:else if item.href === '/checks'}
						<span class="ml-auto text-[11.5px] text-[var(--sb-warning)]">3</span>
					{:else if item.href === '/runs'}
						<span class="ml-auto h-1.5 w-1.5 rounded-full bg-[var(--sb-success)]"></span>
					{/if}
				</a>
			{/each}
		{/each}

		<div class="flex-1"></div>

		{#each footerItems as item (item.href)}
			{@const Glyph = item.icon}
			<a
				href={item.href}
				class="text-[var(--sidebar-foreground)] hover:bg-[var(--sb-hover)] hover:text-foreground flex items-center gap-2.5 rounded-md px-3 py-[7px] text-[13px]"
			>
				<span class="grid w-4 place-items-center opacity-80"><Glyph size={15} /></span>
				{item.label}
			</a>
		{/each}
	</nav>

	<div class="mt-2 border-t border-[var(--sidebar-border)] pt-2.5">
		<div class="text-[var(--sidebar-foreground)] flex items-center gap-2 px-2.5 py-1.5 text-[12.5px]">
			<span
				class="bg-primary grid h-[22px] w-[22px] place-items-center rounded-[2px] text-[10px] font-semibold text-white"
				>AD</span
			>
			admin
		</div>
	</div>
</aside>

<style>
	.app-sidebar {
		color: var(--foreground);
		box-shadow: 8px 0 30px rgba(15, 17, 20, 0.05);
	}
	:global(.dark) .app-sidebar {
		color: #f1f1ee;
		box-shadow: none;
	}
	.project-row:hover {
		background: rgba(255, 255, 255, 0.04);
	}
	.nav-count {
		color: #707782;
	}
	/* default (light theme): show the dark-colored logo */
	.logo-dark {
		display: none;
	}
	.logo-light {
		display: block;
	}
	/* dark theme: show the light-colored logo */
	:global(.dark) .logo-dark {
		display: block;
	}
	:global(.dark) .logo-light {
		display: none;
	}
</style>
