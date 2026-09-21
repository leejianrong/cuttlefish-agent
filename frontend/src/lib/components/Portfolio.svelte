<script lang="ts">
  import type { FleetClient, ProjectSummary } from "../api";
  import ProjectCard from "./ProjectCard.svelte";
  import RegisterProjectForm from "./RegisterProjectForm.svelte";

  let {
    client,
    onOpenProject,
    onDisconnect,
    onShowGallery,
  }: {
    client: FleetClient;
    onOpenProject: (id: string) => void;
    onDisconnect: () => void;
    onShowGallery: () => void;
  } = $props();

  let projects = $state<ProjectSummary[]>([]);
  let loaded = $state(false);
  let unreachable = $state(false);

  async function refresh() {
    try {
      const result = await client.listProjects();
      projects = result.projects;
      unreachable = false;
    } catch {
      unreachable = true;
    } finally {
      loaded = true;
    }
  }

  $effect(() => {
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  });

  async function stop(id: string) {
    await client.stopProject(id);
    await refresh();
  }

  async function remove(id: string) {
    await client.deregisterProject(id);
    await refresh();
  }
</script>

<div class="page">
  <header class="topbar">
    <h1>Fleet</h1>
    <div class="topbar-right">
      <span class="endpoint mono">{client.baseUrl}</span>
      <button class="ghost" onclick={onShowGallery}>Sprite gallery</button>
      <button class="ghost" onclick={onDisconnect}>Disconnect</button>
    </div>
  </header>

  {#if unreachable}
    <p class="warning">Lost connection to the daemon -- retrying…</p>
  {/if}

  <div class="grid">
    {#each projects as project (project.id)}
      <ProjectCard
        {project}
        onOpen={() => onOpenProject(project.id)}
        onStop={() => stop(project.id)}
        onRemove={() => remove(project.id)}
      />
    {/each}
    <RegisterProjectForm {client} onRegistered={refresh} />
  </div>

  {#if loaded && projects.length === 0}
    <p class="empty-state">No projects registered yet -- add one above.</p>
  {/if}
</div>

<style>
  .page {
    max-width: 72rem;
    margin: 0 auto;
    padding: 2rem 1.5rem 4rem;
  }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.75rem;
  }

  h1 {
    font-size: 1.4rem;
    margin: 0;
  }

  .topbar-right {
    display: flex;
    align-items: center;
    gap: 0.9rem;
  }

  .endpoint {
    color: var(--text-faint);
    font-size: 0.78rem;
  }

  .warning {
    background: var(--status-blocked-bg);
    color: var(--status-blocked-fg);
    padding: 0.6rem 0.9rem;
    border-radius: 8px;
    font-size: 0.85rem;
    margin-bottom: 1.25rem;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr));
    gap: 1rem;
  }

  .empty-state {
    color: var(--text-faint);
    margin-top: 2rem;
  }

  button.ghost {
    padding: 0.4rem 0.8rem;
    border-radius: 7px;
    font-size: 0.82rem;
    background: none;
    border: 1px solid var(--border);
    color: var(--text-muted);
  }
</style>
