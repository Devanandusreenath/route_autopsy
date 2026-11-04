import { describe, expect, it } from "vitest";
import { z } from "zod";
import { request } from "@/lib/api/client";
import { resolveConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";

const cfg = resolveConfig({ mode: "backend", baseUrl: "http://localhost:8000", timeoutMs: "50" });
const schema = z.object({ ok: z.boolean() });
const res = (status: number, body: string) =>
  (async () => new Response(body, { status })) as unknown as typeof fetch;

async function err(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
  } catch (e) {
    return e as ApiError;
  }
  throw new Error("expected rejection");
}

describe("config", () => {
  it("backend mode without URL is misconfigured, not demo", () => {
    const c = resolveConfig({ mode: "backend" });
    expect(c.mode).toBe("backend");
    expect(c.misconfigured).toBe(true);
  });
  it("defaults to demo when no URL", () => expect(resolveConfig({}).mode).toBe("demo"));
});

describe("request errors", () => {
  it("misconfigured backend throws config error", async () => {
    const e = await err(
      request({ path: "/x", responseSchema: schema }, resolveConfig({ mode: "backend" })),
    );
    expect(e.category).toBe("config");
  });
  it("network failure is retryable network error", async () => {
    const f = (async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    const e = await err(request({ path: "/x", responseSchema: schema }, cfg, f));
    expect([e.category, e.retryable]).toEqual(["network", true]);
  });
  it("times out via AbortController", async () => {
    const f = ((_u: string, init: RequestInit) =>
      new Promise((_r, rej) =>
        init.signal!.addEventListener("abort", () =>
          rej(new DOMException("aborted", "AbortError")),
        ),
      )) as unknown as typeof fetch;
    const e = await err(request({ path: "/x", responseSchema: schema }, cfg, f));
    expect(e.category).toBe("timeout");
  });
  it.each([
    [400, "validation", false],
    [401, "unauthorized", false],
    [403, "forbidden", false],
    [404, "not_found", false],
    [422, "validation", false],
    [500, "server", true],
  ])("HTTP %i -> %s", async (status, category, retryable) => {
    const e = await err(
      request(
        { path: "/x", responseSchema: schema },
        cfg,
        res(status, '{"detail":"Traceback secret"}'),
      ),
    );
    expect([e.category, e.status, e.retryable]).toEqual([category, status, retryable]);
    if (status === 500) expect(e.message).not.toContain("Traceback");
  });
  it("parses FastAPI 422 field errors", async () => {
    const e = await err(
      request(
        { path: "/x", responseSchema: schema },
        cfg,
        res(422, '{"detail":[{"loc":["body","origin"],"msg":"field required"}]}'),
      ),
    );
    expect(e.fieldErrors).toEqual(["origin: field required"]);
  });
  it("invalid JSON", async () => {
    const e = await err(request({ path: "/x", responseSchema: schema }, cfg, res(200, "<html>")));
    expect(e.category).toBe("invalid_json");
  });
  it("unexpected structure", async () => {
    const e = await err(
      request({ path: "/x", responseSchema: schema }, cfg, res(200, '{"ok":"yes"}')),
    );
    expect(e.category).toBe("unexpected_response");
  });
  it("valid response passes through", async () => {
    await expect(
      request({ path: "/x", responseSchema: schema }, cfg, res(200, '{"ok":true}')),
    ).resolves.toEqual({ ok: true });
  });
});
