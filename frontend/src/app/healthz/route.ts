/** Liveness for the web container. Deliberately does not touch the API: the site can still
 * render, hold intake drafts and explain itself while the backend is down, so tying this to
 * upstream health would take the frontend down with it. */
export function GET(): Response {
  return Response.json({ status: "ok" });
}
