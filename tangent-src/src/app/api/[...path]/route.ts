import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const hopByHopHeaders = [
  "connection",
  "content-encoding",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
];

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
  const target = new URL(path.map(encodeURIComponent).join("/"), `${backendUrl.replace(/\/+$/, "")}/`);
  target.search = new URL(request.url).search;

  const headers = new Headers(request.headers);
  for (const name of hopByHopHeaders) headers.delete(name);

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const init: RequestInit & { duplex: "half" } = {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    duplex: "half",
    cache: "no-store",
    redirect: "manual",
  };
  const upstream = await fetch(target, init);

  const responseHeaders = new Headers(upstream.headers);
  for (const name of hopByHopHeaders) responseHeaders.delete(name);
  responseHeaders.set("Cache-Control", "no-cache, no-transform");
  if (responseHeaders.get("Content-Type")?.startsWith("text/event-stream")) {
    responseHeaders.set("X-Accel-Buffering", "no");
  }

  const bodyForbidden =
    request.method === "HEAD" || [204, 205, 304].includes(upstream.status);
  return new Response(bodyForbidden ? null : upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
