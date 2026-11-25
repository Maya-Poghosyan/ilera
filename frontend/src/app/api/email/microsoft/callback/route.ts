import type { NextRequest } from "next/server";

import { finishMailboxCallback } from "@/lib/server/mailbox-callback";

export function GET(request: NextRequest): Promise<Response> {
  return finishMailboxCallback(request, "microsoft");
}
