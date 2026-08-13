import "server-only";

import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

/** Name of the httpOnly cookie holding the API token. Never readable from JavaScript. */
export const SESSION_COOKIE = "ilera_session";

/** Where the FastAPI backend lives, read per request so the deployed image isn't tied to a URL.
 *
 * Deliberately not `NEXT_PUBLIC_`: that would inline the value into the browser bundle at build
 * time, which is what made a missing build arg silently produce same-origin requests. */
function apiUrl(): string {
  return process.env.API_URL || "http://localhost:8000";
}

export async function sessionToken(): Promise<string | undefined> {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

export function sessionCookieOptions(maxAgeSeconds: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: maxAgeSeconds,
  };
}

/** Call the backend with the caller's session attached. */
export async function callApi(
  path: string,
  init: RequestInit & { token?: string | null } = {},
): Promise<Response> {
  const { token, headers, ...rest } = init;
  const auth = token === undefined ? await sessionToken() : token;
  return fetch(`${apiUrl()}${path}`, {
    ...rest,
    headers: {
      ...(headers as Record<string, string> | undefined),
      ...(auth ? { Authorization: `Bearer ${auth}` } : {}),
    },
    cache: "no-store",
  });
}

/** Headers worth returning to the browser. The rest (hop-by-hop, encoding) belong to the
 * connection between this server and the backend, not to the client's. */
const PASS_THROUGH = ["content-type", "content-disposition", "cache-control"];

/** Forward a browser request to the backend and relay the reply verbatim.
 *
 * The body is streamed rather than parsed so filled PDFs pass through as bytes. */
export async function proxyToApi(
  request: NextRequest,
  path: string,
): Promise<Response> {
  const search = request.nextUrl.search;
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const contentType = request.headers.get("content-type");
  const upstream = await callApi(`${path}${search}`, {
    method: request.method,
    headers: contentType ? { "content-type": contentType } : undefined,
    body: hasBody ? await request.text() : undefined,
  });
  const headers = new Headers();
  for (const name of PASS_THROUGH) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}
