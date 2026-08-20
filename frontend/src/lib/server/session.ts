import "server-only";

import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE, callApi, sessionCookieOptions } from "./api-proxy";

/** Seconds until the token expires, from its own `exp` claim.
 *
 * The signature doesn't need checking — the backend just issued this over a trusted connection,
 * and the claim is only used to decide when the browser may forget the cookie. */
function secondsUntilExpiry(token: string): number {
  const { exp } = JSON.parse(
    Buffer.from(token.split(".")[1], "base64url").toString("utf8"),
  ) as { exp: number };
  return Math.max(1, Math.floor(exp - Date.now() / 1000));
}

/** Sign up or log in, keeping the token server-side.
 *
 * The browser gets the user and an httpOnly cookie; the token itself is never in a response
 * body reachable from JavaScript, so an XSS bug can't read it out of storage. */
export async function startSession(
  request: NextRequest,
  path: "/api/auth/signup" | "/api/auth/login",
): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await callApi(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await request.text(),
      token: null,
    });
  } catch (err) {
    console.error(`api proxy: POST ${path} failed`, err);
    return Response.json({ detail: "The API is unreachable." }, { status: 502 });
  }
  const body = await upstream.json();
  if (!upstream.ok) {
    return Response.json(body, { status: upstream.status });
  }
  const { token, user } = body as { token: string; user: unknown };
  (await cookies()).set(
    SESSION_COOKIE,
    token,
    sessionCookieOptions(secondsUntilExpiry(token)),
  );
  return Response.json(user);
}
