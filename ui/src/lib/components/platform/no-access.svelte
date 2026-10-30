<script lang="ts">
	import LockIcon from '@lucide/svelte/icons/lock';

	let { what, requires }: { what: string; requires: string } = $props();
</script>

<div class="grid min-h-0 flex-1 place-items-center p-8">
	<div class="max-w-md text-center">
		<div class="text-muted-foreground mx-auto mb-3 grid h-9 w-9 place-items-center rounded-md border border-border">
			<LockIcon size={16} />
		</div>
		<h2 class="text-[14px] font-semibold">You don't have access to {what}</h2>
		<p class="text-muted-foreground mt-1.5 text-[13px]">Ask an administrator for a role that allows it (<code>{requires}</code>).</p>
	</div>
</div>
