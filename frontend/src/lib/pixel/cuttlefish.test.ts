// Unit: the pure pixel-art data layer (slice D2) -- no rendering, no DOM. The
// actual rendered shape is verified visually (Playwright, by hand); this covers
// the invariants a rendering bug or a future edit could silently break.

import { describe, expect, it } from "vitest";
import type { RoleStatus } from "../api";
import { CUTTLEFISH_FRAMES, STATUS_GLYPH, paletteFor } from "./cuttlefish";

const ALL_STATUSES: RoleStatus[] = ["queued", "working", "blocked", "done", "failed"];

describe("CUTTLEFISH_FRAMES", () => {
  it("both frames are the same rectangular shape", () => {
    const { a, b } = CUTTLEFISH_FRAMES;
    expect(a.length).toBe(b.length);
    const widths = new Set([...a, ...b].map((row) => row.length));
    expect(widths.size).toBe(1);
  });

  it("only uses characters every status's palette actually defines", () => {
    const usedChars = new Set(
      [...CUTTLEFISH_FRAMES.a, ...CUTTLEFISH_FRAMES.b].flatMap((row) => row.split("")),
    );
    usedChars.delete(".");
    for (const status of ALL_STATUSES) {
      const palette = paletteFor(status);
      for (const char of usedChars) {
        expect(palette[char], `palette for ${status} is missing '${char}'`).toBeDefined();
      }
    }
  });
});

describe("paletteFor", () => {
  it("gives every status a distinct head color", () => {
    const heads = ALL_STATUSES.map((status) => paletteFor(status).H);
    expect(new Set(heads).size).toBe(ALL_STATUSES.length);
  });

  it("keeps eyes and pupils constant across every status", () => {
    const palettes = ALL_STATUSES.map(paletteFor);
    for (const key of ["E", "P"] as const) {
      const values = new Set(palettes.map((p) => p[key]));
      expect(values.size).toBe(1);
    }
  });

  it("returns valid CSS hex colors", () => {
    for (const status of ALL_STATUSES) {
      for (const color of Object.values(paletteFor(status))) {
        expect(color).toMatch(/^#[0-9a-f]{6}$/i);
      }
    }
  });
});

describe("STATUS_GLYPH", () => {
  it("has an entry for every status, working's own being the deliberate exception", () => {
    for (const status of ALL_STATUSES) {
      expect(Object.hasOwn(STATUS_GLYPH, status)).toBe(true);
    }
  });

  it("working has no glyph -- the wiggle animation is the signal instead", () => {
    expect(STATUS_GLYPH.working).toBeNull();
  });

  it("every non-working status has a single-character glyph", () => {
    for (const status of ALL_STATUSES.filter((s) => s !== "working")) {
      expect(STATUS_GLYPH[status]).not.toBeNull();
      expect([...(STATUS_GLYPH[status] ?? "")].length).toBe(1);
    }
  });
});
