<script lang="ts">
	import SunIcon from '@lucide/svelte/icons/sun';
	import MoonIcon from '@lucide/svelte/icons/moon';
	import { theme, toggleTheme } from '$lib/theme.svelte';

	type Props = {
		title: string;
		breadcrumb?: string;
		children?: import('svelte').Snippet;
	};
	let { title, breadcrumb = 'waffle-shop / production', children }: Props = $props();
</script>

<div class="app-topbar flex h-[52px] shrink-0 items-center gap-3 border-b border-border px-5">
	<h1 class="text-[15px] font-semibold">{title}</h1>
	<span class="text-muted-foreground text-[12.5px]">{breadcrumb}</span>
	<div class="ml-auto flex items-center gap-2.5">
		<span class="text-muted-foreground mr-1 flex items-center gap-[7px] text-[12px]">
			<span class="h-[7px] w-[7px] rounded-full bg-[var(--sb-success)]"></span>
			Synced 4s ago
		</span>
		{#if children}{@render children()}{/if}
		<button
			class="bg-card text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] grid h-8 w-8 place-items-center rounded-md border border-border"
			aria-label="Toggle theme"
			onclick={toggleTheme}
		>
			{#if theme.value === 'dark'}
				<SunIcon size={14} />
			{:else}
				<MoonIcon size={14} />
			{/if}
		</button>
	</div>
</div>

<style>
	.app-topbar {
		background: color-mix(in srgb, var(--background) 94%, transparent);
		backdrop-filter: blur(12px);
	}
</style>
