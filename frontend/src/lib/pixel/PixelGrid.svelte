<script lang="ts">
  import type { PixelFrame } from "./cuttlefish";

  let {
    frame,
    palette,
    pixelSize = 3,
  }: { frame: PixelFrame; palette: Record<string, string>; pixelSize?: number } = $props();

  const cols = $derived(frame[0]?.length ?? 0);
  const rows = $derived(frame.length);
</script>

<div
  class="pixel-grid"
  style:--cols={cols}
  style:--rows={rows}
  style:--px="{pixelSize}px"
  aria-hidden="true"
>
  {#each frame as row, y (y)}
    {#each row.split("") as cell, x (x)}
      {#if cell !== "."}
        <span class="px" style:grid-column={x + 1} style:grid-row={y + 1} style:background={palette[cell]}
        ></span>
      {/if}
    {/each}
  {/each}
</div>

<style>
  .pixel-grid {
    display: grid;
    grid-template-columns: repeat(var(--cols), var(--px));
    grid-template-rows: repeat(var(--rows), var(--px));
  }

  .px {
    width: var(--px);
    height: var(--px);
  }
</style>
