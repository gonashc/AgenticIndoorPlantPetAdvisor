import { describe, expect, it } from "vitest";

import { parseSseBuffer } from "@advisor/api-client";

describe("parseSseBuffer", () => {
  it("parses complete SSE events and preserves an incomplete event", () => {
    const completed = JSON.stringify({ event: "progress", data: { percent: 20 } });
    const result = parseSseBuffer(`id: 1\r\ndata: ${completed}\r\n\r\ndata: {"event":"comp`);

    expect(result.events).toEqual([{ event: "progress", data: { percent: 20 } }]);
    expect(result.remainder).toBe('data: {"event":"comp');
  });

  it("joins multiple data lines before parsing JSON", () => {
    const result = parseSseBuffer('event: completed\ndata: {"event":"completed",\ndata: "sequence":2}\n\n');

    expect(result.events).toEqual([{ event: "completed", sequence: 2 }]);
    expect(result.remainder).toBe("");
  });
});
