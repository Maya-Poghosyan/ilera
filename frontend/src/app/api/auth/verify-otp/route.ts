import type { NextRequest } from "next/server";

import { startSession } from "@/lib/server/session";

// Validates the OTP, issues the session cookie, and returns the user.
export function POST(request: NextRequest): Promise<Response> {
  return startSession(request, "/api/auth/verify-otp");
}
