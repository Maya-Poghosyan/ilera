/** Thrown for any non-2xx reply, carrying the status so callers can tell "the backend is down"
 * from "you may not read this case". */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    path: string,
  ) {
    super(`API ${path} failed: ${status}`);
    this.name = "ApiError";
  }

  /** A deploy, restart or blip rather than anything wrong with the request. */
  get isTransient(): boolean {
    return this.status === 0 || this.status >= 502;
  }
}

const RETRY_DELAYS_MS = [400, 1200];

/** A backend restart takes seconds, so a request that lands mid-restart should wait rather than
 * fail the page. Only reads are retried: replaying a POST could file a second application. */
function shouldRetry(method: string, err: unknown): boolean {
  return (
    (method === "GET" || method === "HEAD") &&
    err instanceof ApiError &&
    err.isTransient
  );
}

// Paths stay relative: `/api/*` is served by this app's own route handlers, which forward to the
// backend and attach the session cookie as a bearer token. Nothing here knows the API's URL, and
// no token is reachable from client JavaScript.
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? "GET";
  for (let attempt = 0; ; attempt++) {
    try {
      return await sendOnce<T>(path, init);
    } catch (err) {
      if (attempt >= RETRY_DELAYS_MS.length || !shouldRetry(method, err)) throw err;
      await new Promise((r) => setTimeout(r, RETRY_DELAYS_MS[attempt]));
    }
  }
}

async function sendOnce<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      headers: { "content-type": "application/json" },
      ...init,
    });
  } catch {
    // The browser couldn't reach our own server: offline, or a frontend deploy in progress.
    throw new ApiError(0, path);
  }
  if (!res.ok) {
    throw new ApiError(res.status, path);
  }
  return res.json() as Promise<T>;
}
