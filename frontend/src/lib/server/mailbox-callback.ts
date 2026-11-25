import "server-only";

import type { NextRequest } from "next/server";

import { callApi } from "@/lib/server/api-proxy";

/** The provider returns here so the existing SameSite=Lax session cookie binds the callback to
 * the signed-in user.
 * - The code goes to FastAPI in a POST body, never a log
 * - The dashboard gets only `mailbox=connected|failed`; no provider detail or query parameter */
export async function finishMailboxCallback(request: NextRequest, provider: "microsoft" | "google"): Promise<Response> {
  const state = request.nextUrl.searchParams.get("state");
  const code = request.nextUrl.searchParams.get("code");
  const denied = request.nextUrl.searchParams.has("error");
  let result = "failed";
  if (state && state.length <= 512 && (!code || code.length <= 16384)) {
    try {
      const upstream = await callApi(`/api/email/${provider}/callback`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ state, code, denied }),
      });
      result = upstream.ok ? "connected" : "failed";
      await upstream.body?.cancel();
    } catch {
      // Fixed UI status; network errors can contain the original request URL.
    }
  }
  // Relative, so the browser stays on the host it came back to (request.url can name another).
  return new Response(null, { status: 303, headers: {
    location: `/dashboard?${new URLSearchParams({ mailbox: result, provider })}`,
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
  } });
}
