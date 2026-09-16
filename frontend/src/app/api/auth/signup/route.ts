import type { NextRequest } from "next/server";

import { callApi } from "@/lib/server/api-proxy";

// Signup no longer issues a session — the account is created but a JWT is only issued
// after the user clicks the verification link.  startSession is not used here.
export async function POST(request: NextRequest): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await callApi("/api/auth/signup", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await request.text(),
      token: null,
    });
  } catch (err) {
    console.error("api proxy: POST /api/auth/signup failed", err);
    return Response.json({ detail: "The API is unreachable." }, { status: 502 });
  }
  const body = await upstream.json();
  return Response.json(body, { status: upstream.status });
}
