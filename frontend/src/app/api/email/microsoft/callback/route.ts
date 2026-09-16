import { NextResponse, type NextRequest } from "next/server";

import { callApi } from "@/lib/server/api-proxy";

/** Microsoft returns here so the existing SameSite=Lax session cookie binds the
 * callback to the signed-in user. Codes go to FastAPI in a POST body, never a log. */
export async function GET(request: NextRequest): Promise<Response> {
  const state = request.nextUrl.searchParams.get("state");
  const code = request.nextUrl.searchParams.get("code");
  const denied = request.nextUrl.searchParams.has("error");
  let result = "failed";
  if (state && state.length <= 512 && (!code || code.length <= 16384)) {
    try {
      const upstream = await callApi("/api/email/microsoft/callback", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ state, code, denied }),
      });
      result = upstream.ok ? "connected" : "failed";
      // Do not forward provider details, tokens, or callback query parameters.
      await upstream.body?.cancel();
    } catch {
      // Fixed UI status; network errors can contain the original request URL.
    }
  }
  const target = new URL("/dashboard", request.url);
  target.searchParams.set("mailbox", result);
  const response = NextResponse.redirect(target, 303);
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}
