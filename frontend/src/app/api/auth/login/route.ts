import type { NextRequest } from "next/server";

import { startSession } from "@/lib/server/session";

export function POST(request: NextRequest): Promise<Response> {
  return startSession(request, "/api/auth/login");
}
