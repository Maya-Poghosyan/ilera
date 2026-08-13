import type { NextRequest } from "next/server";

import { proxyToApi } from "@/lib/server/api-proxy";

/** Everything the browser asks of `/api/*` is served from this origin and forwarded here.
 *
 * The backend's URL and the session token stay on the server: the client never learns either,
 * so no API host is baked into the bundle and there is no cross-origin request to allow.
 * `/api/auth/{signup,login,logout}` have their own handlers — more specific routes win. */
async function handler(
  request: NextRequest,
  ctx: RouteContext<"/api/[...path]">,
): Promise<Response> {
  const { path } = await ctx.params;
  return proxyToApi(request, `/api/${path.map(encodeURIComponent).join("/")}`);
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
