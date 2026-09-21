<script lang="ts">
  import type { EpisodicEventView } from "../api";

  let { events }: { events: EpisodicEventView[] } = $props();

  function summarize(event: EpisodicEventView): string {
    const p = event.payload;
    switch (event.event_type) {
      case "TaskSubmitted":
        return `submitted: ${p.text}`;
      case "DelegationStarted":
        return `round started: ${p.task_text}`;
      case "DelegationCompleted":
        return `round completed: ${p.summary}`;
      case "DelegationRefused":
        return `refused: ${p.reason}`;
      case "DelegationFailed":
        return `failed: ${p.reason}`;
      case "SteeringMessage":
        return `operator: ${p.text}`;
      case "HandoverWritten":
        return `context handover written`;
      case "TaskCompleted":
        return `done: ${p.result}`;
      case "TaskFailed":
        return `failed: ${p.error}`;
      default:
        return JSON.stringify(p);
    }
  }
</script>

<div class="log">
  {#if events.length === 0}
    <p class="empty">no events yet</p>
  {/if}
  {#each events as event (event.seq)}
    <div class="row">
      <span class="ts mono">{new Date(event.ts).toLocaleTimeString()}</span>
      {#if event.payload.role}
        <span class="role mono">{event.payload.role}</span>
      {/if}
      <span class="type">{event.event_type}</span>
      <span class="text">{summarize(event)}</span>
    </div>
  {/each}
</div>

<style>
  .log {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    max-height: 22rem;
    overflow-y: auto;
    font-size: 0.82rem;
  }

  .empty {
    color: var(--text-faint);
    font-style: italic;
  }

  .row {
    display: grid;
    grid-template-columns: 5.5rem 5.5rem 9rem 1fr;
    gap: 0.6rem;
    align-items: baseline;
    padding: 0.3rem 0;
    border-bottom: 1px solid var(--border);
  }

  .ts {
    color: var(--text-faint);
    font-size: 0.75rem;
  }

  .role {
    color: var(--accent);
    font-size: 0.75rem;
  }

  .type {
    color: var(--text-muted);
    font-weight: 600;
    font-size: 0.75rem;
  }

  .text {
    color: var(--text);
    overflow-wrap: anywhere;
  }
</style>
