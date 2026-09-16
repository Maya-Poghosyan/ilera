import type { NextRequest } from "next/server";

import { startSession } from "@/lib/server/session";

// Validates the one-time token, marks the account verified, and issues the session cookie.
export function POST(request: NextRequest): Promise<Response> {
  return startSession(request, "/api/auth/verify-email");
}
