import type { NextRequest } from "next/server";

import { callApi } from "@/lib/server/api-proxy";

// Login now sends an OTP rather than issuing a session directly.
// The session cookie is set by /api/auth/verify-otp once the code is confirmed.
export async function POST(request: NextRequest): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await callApi("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await request.text(),
      token: null,
    });
  } catch (err) {
    console.error("api proxy: POST /api/auth/login failed", err);
    return Response.json({ detail: "The API is unreachable." }, { status: 502 });
  }
  const body = await upstream.json();
  return Response.json(body, { status: upstream.status });
}
