<script lang="ts">
  import { FleetClient } from "./lib/api";
  import ConnectScreen from "./lib/components/ConnectScreen.svelte";
  import Portfolio from "./lib/components/Portfolio.svelte";
  import ProjectDetail from "./lib/components/ProjectDetail.svelte";
  import SpriteGallery from "./lib/components/SpriteGallery.svelte";
  import { clearConnection, loadConnection, saveConnection } from "./lib/session";

  const remembered = loadConnection();
  let client = $state<FleetClient | null>(
    remembered ? new FleetClient(remembered.baseUrl, remembered.token) : null,
  );
  let openProjectId = $state<string | null>(null);
  let showGallery = $state(false);

  function onConnected(newClient: FleetClient) {
    client = newClient;
    saveConnection({ baseUrl: newClient.baseUrl, token: newClient.token });
  }

  function disconnect() {
    client = null;
    openProjectId = null;
    clearConnection();
  }
</script>

{#if showGallery}
  <SpriteGallery onBack={() => (showGallery = false)} />
{:else if !client}
  <ConnectScreen onConnected={onConnected} onShowGallery={() => (showGallery = true)} />
{:else if openProjectId}
  <ProjectDetail {client} projectId={openProjectId} onBack={() => (openProjectId = null)} />
{:else}
  <Portfolio
    {client}
    onOpenProject={(id) => (openProjectId = id)}
    onDisconnect={disconnect}
    onShowGallery={() => (showGallery = true)}
  />
{/if}
