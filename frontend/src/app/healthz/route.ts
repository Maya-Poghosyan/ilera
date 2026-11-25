/** Liveness for the web container. Deliberately does not touch the API: the site can still
 * render, hold intake drafts and explain itself while the backend is down, so tying this to
 * upstream health would take the frontend down with it.
 * - `build`: the commit this image was built from; the deploy waits until it is serving. */
export function GET(): Response {
  return Response.json({ status: "ok", build: process.env.BUILD_SHA ?? "dev" });
}
