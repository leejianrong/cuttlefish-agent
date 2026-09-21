<script lang="ts">
  import type { ProjectSummary } from "../api";
  import StatusChip from "./StatusChip.svelte";

  let {
    project,
    onOpen,
    onStop,
    onRemove,
  }: {
    project: ProjectSummary;
    onOpen: () => void;
    onStop: () => void;
    onRemove: () => void;
  } = $props();

  const roleEntries = $derived(Object.entries(project.status));
</script>

<article class="card">
  <header>
    <button class="title" onclick={onOpen}>{project.name}</button>
    {#if project.running}
      <span class="running-dot" title="a team is running"></span>
    {/if}
  </header>
  <p class="root mono">{project.root}</p>

  {#if roleEntries.length > 0}
    <div class="roles">
      {#each roleEntries as [role, status] (role)}
        <div class="role-row">
          <span class="role-name">{role}</span>
          <StatusChip {status} />
        </div>
      {/each}
    </div>
  {:else}
    <p class="empty">no roles registered yet</p>
  {/if}

  <footer>
    {#if project.running}
      <button class="danger" onclick={onStop}>Stop</button>
    {:else}
      <button class="primary" onclick={onOpen}>Start…</button>
    {/if}
    <button class="ghost" onclick={onRemove}>Remove</button>
  </footer>
</article>

<style>
  .card {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.1rem 1.2rem;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .title {
    background: none;
    border: none;
    padding: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
    text-align: left;
  }

  .title:hover {
    color: var(--accent);
  }

  .running-dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 999px;
    background: var(--status-working-fg);
    animation: pulse 1.4s ease-in-out infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }

  .root {
    color: var(--text-faint);
    font-size: 0.78rem;
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .roles {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    margin: 0.2rem 0;
  }

  .role-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .role-name {
    font-size: 0.85rem;
    color: var(--text-muted);
  }

  .empty {
    color: var(--text-faint);
    font-size: 0.82rem;
    font-style: italic;
    margin: 0.2rem 0;
  }

  footer {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.4rem;
  }

  button.primary,
  button.danger,
  button.ghost {
    padding: 0.4rem 0.85rem;
    border-radius: 7px;
    font-size: 0.82rem;
    font-weight: 600;
    border: 1px solid transparent;
  }

  button.primary {
    background: var(--accent);
    color: var(--accent-text);
  }

  button.danger {
    background: var(--status-failed-bg);
    color: var(--status-failed-fg);
  }

  button.ghost {
    background: none;
    border-color: var(--border);
    color: var(--text-muted);
    margin-left: auto;
  }
</style>
