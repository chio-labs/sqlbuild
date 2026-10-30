<script lang="ts">
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import GatedButton from '$lib/components/platform/gated-button.svelte';
	import NoAccess from '$lib/components/platform/no-access.svelte';
	import { app } from '$lib/state/app.svelte';
	import AccountCard from './account-card.svelte';
	import { createServiceAccountsState } from './state.svelte';

	const sa = createServiceAccountsState();
	const allowed = $derived(app.can('user.manage') || app.can('token.manage'));

	let creating = $state(false);
	let name = $state('');
	let description = $state('');
	let query = $state('');
	const q = $derived(query.trim().toLowerCase());
	const shown = $derived(sa.services.filter((a) => !q || `${a.name} ${a.description ?? ''} ${a.owner ?? ''}`.toLowerCase().includes(q)));

	function create() {
		void sa.createAccount(name.trim(), description.trim()).then(() => {
			if (!sa.error) {
				name = '';
				description = '';
				creating = false;
			}
		});
	}
</script>

<AppTopbar title="Service accounts">
	<Button variant="outline" size="sm" onclick={() => sa.refresh()}>↻ Refresh</Button>
</AppTopbar>

{#if !allowed}
	<NoAccess what="service accounts" requires="user.manage or token.manage" />
{:else}
	<div class="min-h-0 flex-1 overflow-auto px-6 pt-4 pb-6">
		<div class="intro">
			<p>
				Service accounts are for scripts and CI. They sign in only with API tokens, and get roles like people do in <a href="/admin/roles">Roles &amp; approvals</a>.
				Each token's secret is shown once when you create it; after that, only its first characters are kept for recognising it.
			</p>
			<p class="faint">People don't need tokens: they use <code>sqb login</code>. Tokens for code locations are on each <a href="/locations">location's page</a>.</p>
		</div>

		<div class="bar">
			<input class="field search" placeholder="Search service accounts" bind:value={query} aria-label="Search service accounts" />
			<GatedButton requires="user.manage" onclick={() => (creating = !creating)}>New service account</GatedButton>
		</div>
		{#if creating}
			<div class="bar">
				<input class="field" placeholder="Name, e.g. svc-exports" bind:value={name} aria-label="Service account name" />
				<input class="field wide" placeholder="What it's for" bind:value={description} aria-label="What it's for" />
				<GatedButton requires="user.manage" variant="default" busy={sa.busy === 'create-account'} disabled={!name.trim()} title="Give it a name" onclick={create}>Create</GatedButton>
				<Button variant="ghost" size="sm" onclick={() => (creating = false)}>Cancel</Button>
			</div>
		{/if}
		{#if sa.error && sa.error.account === null}<p class="err">{sa.error.message}</p>{/if}
		{#if sa.created}
			<p class="created">
				Created <code>{sa.created.name}</code>. It can't do anything yet: create a token below, then give it a role in <a href="/admin/roles">Roles &amp; approvals</a>.
				<button onclick={() => sa.dismissCreated()}>Dismiss</button>
			</p>
		{/if}

		{#each shown as account (account.name)}
			<AccountCard {account} {sa} />
		{:else}
			<p class="muted">
				{#if sa.accounts.error}Couldn't load service accounts: {sa.accounts.error}{:else if sa.accounts.loading && !sa.accounts.data}Loading…{:else if sa.services.length}No service accounts match the search.{:else}No service accounts yet.{/if}
			</p>
		{/each}
	</div>
{/if}

<style>
	.intro {
		max-width: 900px;
		margin-bottom: 14px;
		font-size: 12.5px;
		line-height: 1.55;
	}
	.intro p + p {
		margin-top: 4px;
	}
	a {
		color: var(--primary);
	}
	code {
		font-family: var(--font-mono);
		font-size: 12px;
	}
	.bar {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 12px;
	}
	.field {
		height: 32px;
		padding: 0 9px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--background);
		color: var(--foreground);
		font-size: 12.5px;
	}
	.field {
		width: 240px;
	}
	.field.wide {
		width: 340px;
	}
	.field.search {
		width: 280px;
	}
	.created {
		margin-bottom: 12px;
		padding: 8px 12px;
		border: 1px solid color-mix(in srgb, var(--sb-success) 40%, var(--border));
		border-radius: 2px;
		background: color-mix(in srgb, var(--sb-success) 7%, var(--background));
		font-size: 12.5px;
	}
	.created button {
		margin-left: 8px;
		color: var(--muted-foreground);
	}
	.muted {
		color: var(--muted-foreground);
		font-size: 12.5px;
	}
	.faint {
		color: var(--sb-text-faint);
	}
	.err {
		margin-bottom: 10px;
		color: var(--sb-error);
		font-size: 12.5px;
	}
</style>
