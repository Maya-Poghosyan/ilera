/** Where the API lives, for every caller in the app.
 *
 * `NEXT_PUBLIC_*` is inlined at build time, so an image built without the build arg inlines the
 * empty string — and `??` only falls back on undefined, which made every request relative to the
 * frontend's own origin. Treat blank as unset.
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "https://api.ileracare.app";
