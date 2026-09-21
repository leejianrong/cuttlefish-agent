<script lang="ts">
  import { FleetClient, FleetApiError, FleetUnreachableError } from "../api";

  let { onConnected }: { onConnected: (client: FleetClient) => void } = $props();

  let baseUrl = $state("http://127.0.0.1:8420");
  let token = $state("");
  let connecting = $state(false);
  let error = $state<string | null>(null);

  async function connect(event: SubmitEvent) {
    event.preventDefault();
    connecting = true;
    error = null;
    const client = new FleetClient(baseUrl.replace(/\/$/, ""), token.trim());
    try {
      await client.listProjects();
      onConnected(client);
    } catch (err) {
      if (err instanceof FleetUnreachableError) {
        error = err.message;
      } else if (err instanceof FleetApiError) {
        error = err.status === 401 ? "that token was rejected" : err.message;
      } else {
        error = "something went wrong connecting";
      }
    } finally {
      connecting = false;
    }
  }
</script>

<div class="wrap">
  <form onsubmit={connect}>
    <h1>cuttlefish-crew</h1>
    <p class="hint">
      Connect to a running <code>cuttlefish serve</code> -- its base URL and token are
      printed to that process's own stdout at startup.
    </p>

    <label>
      Base URL
      <input type="text" bind:value={baseUrl} placeholder="http://127.0.0.1:8420" required />
    </label>

    <label>
      Token
      <input type="password" bind:value={token} placeholder="x-cuttlefish-token" required />
    </label>

    {#if error}
      <p class="error">{error}</p>
    {/if}

    <button type="submit" disabled={connecting}>
      {connecting ? "Connecting…" : "Connect"}
    </button>
  </form>
</div>

<style>
  .wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
  }

  form {
    width: 100%;
    max-width: 26rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2rem;
  }

  h1 {
    margin: 0 0 0.5rem;
    font-size: 1.3rem;
  }

  .hint {
    color: var(--text-muted);
    font-size: 0.85rem;
    line-height: 1.5;
    margin: 0 0 1.5rem;
  }

  .hint code {
    color: var(--text);
  }

  label {
    display: block;
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-bottom: 1rem;
  }

  input {
    display: block;
    width: 100%;
    margin-top: 0.35rem;
    padding: 0.55rem 0.7rem;
    background: var(--bg-inset);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
  }

  input:focus {
    outline: 2px solid var(--accent);
    outline-offset: -1px;
  }

  button {
    width: 100%;
    padding: 0.65rem;
    border: none;
    border-radius: 8px;
    background: var(--accent);
    color: var(--accent-text);
    font-weight: 600;
  }

  button:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .error {
    color: var(--danger);
    font-size: 0.85rem;
    margin: -0.4rem 0 1rem;
  }
</style>
