import "server-only";

import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE, callApi, sessionCookieOptions } from "./api-proxy";

const DEFAULT_SESSION_SECONDS = 72 * 60 * 60;

/** Seconds until the token expires, from its own `exp` claim.
 *
 * The signature doesn't need checking — the backend just issued this over a trusted connection,
 * and the claim is only used to decide when the browser may forget the cookie. */
function secondsUntilExpiry(token: string): number {
  const payload = token.split(".")[1];
  if (!payload) return DEFAULT_SESSION_SECONDS;
  try {
    const { exp } = JSON.parse(
      Buffer.from(payload, "base64url").toString("utf8"),
    ) as { exp?: number };
    if (!exp) return DEFAULT_SESSION_SECONDS;
    return Math.max(1, Math.floor(exp - Date.now() / 1000));
  } catch {
    return DEFAULT_SESSION_SECONDS;
  }
}

/** Sign up or log in, keeping the token server-side.
 *
 * The browser gets the user and an httpOnly cookie; the token itself is never in a response
 * body reachable from JavaScript, so an XSS bug can't read it out of storage. */
export async function startSession(
  request: NextRequest,
  path: "/api/auth/signup" | "/api/auth/login",
): Promise<Response> {
  const upstream = await callApi(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await request.text(),
    token: null,
  });
  const body = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    return Response.json(body ?? { detail: "Authentication failed" }, {
      status: upstream.status,
    });
  }
  const { token, user } = body as { token: string; user: unknown };
  (await cookies()).set(
    SESSION_COOKIE,
    token,
    sessionCookieOptions(secondsUntilExpiry(token)),
  );
  return Response.json(user);
}
