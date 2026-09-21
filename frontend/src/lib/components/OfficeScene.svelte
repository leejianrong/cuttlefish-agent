<script lang="ts">
  import type { RoleStatus } from "../api";
  import RoleSprite from "./RoleSprite.svelte";

  let { roles }: { roles: { name: string; status: RoleStatus }[] } = $props();
</script>

<div class="office">
  <div class="wall"></div>
  <div class="floor"></div>
  <div class="desks">
    {#each roles as role (role.name)}
      <div class="desk-slot">
        <RoleSprite status={role.status} size={5} />
        <div class="shadow"></div>
        <span class="name mono">{role.name}</span>
      </div>
    {/each}
  </div>
</div>

<style>
  .office {
    position: relative;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--border);
  }

  .wall {
    height: 3.4rem;
    background: linear-gradient(
      180deg,
      var(--bg-inset),
      color-mix(in srgb, var(--bg-inset) 85%, var(--accent) 8%)
    );
  }

  .floor {
    height: 2.6rem;
    background-image: repeating-linear-gradient(
      90deg,
      color-mix(in srgb, var(--bg-inset) 90%, black 6%) 0 2.4rem,
      color-mix(in srgb, var(--bg-inset) 96%, black 0%) 2.4rem 2.6rem
    );
    border-top: 1px solid color-mix(in srgb, var(--border) 100%, black 12%);
  }

  .desks {
    position: absolute;
    inset: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: center;
    gap: 0.4rem 1.7rem;
    padding: 0.5rem 1rem 0.55rem;
  }

  .desk-slot {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
  }

  .shadow {
    width: 2.4rem;
    height: 0.35rem;
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.28);
    margin-top: -0.1rem;
  }

  .name {
    font-size: 0.72rem;
    color: var(--text-muted);
  }
</style>
