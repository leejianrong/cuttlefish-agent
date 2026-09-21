<script lang="ts">
  import type { FleetClient, RoleStatus } from "../api";
  import StatusChip from "./StatusChip.svelte";

  let {
    client,
    projectId,
    role,
    status,
  }: { client: FleetClient; projectId: string; role: string; status: RoleStatus } = $props();

  let message = $state("");
  let sending = $state(false);
  let sent = $state(false);

  async function send() {
    if (!message.trim()) return;
    sending = true;
    sent = false;
    try {
      await client.steerProject(projectId, role, message.trim());
      message = "";
      sent = true;
      setTimeout(() => (sent = false), 2000);
    } finally {
      sending = false;
    }
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      send();
    }
  }
</script>

<div class="role-card">
  <div class="role-head">
    <span class="role-name">{role}</span>
    <StatusChip {status} />
  </div>
  <div class="steer">
    <textarea
      bind:value={message}
      onkeydown={onKeydown}
      placeholder="Redirect {role}'s work… (takes effect at the next round boundary)"
      rows="2"
    ></textarea>
    <button onclick={send} disabled={sending || !message.trim()}>
      {sent ? "Sent" : sending ? "Sending…" : "Send"}
    </button>
  </div>
</div>

<style>
  .role-card {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.15rem;
  }

  .role-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
  }

  .role-name {
    font-weight: 600;
  }

  .steer {
    display: flex;
    gap: 0.6rem;
    align-items: flex-end;
  }

  textarea {
    flex: 1;
    padding: 0.5rem 0.65rem;
    background: var(--bg-inset);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    resize: vertical;
  }

  button {
    padding: 0.5rem 0.9rem;
    border: none;
    border-radius: 8px;
    background: var(--accent);
    color: var(--accent-text);
    font-weight: 600;
    white-space: nowrap;
  }

  button:disabled {
    opacity: 0.5;
  }
</style>
