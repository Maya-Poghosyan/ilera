// Local stand-in for Google sign-in and the Gmail API, for the browser tests.
// - The backend's Google endpoints point here (see backend/tests/e2e_api.py); the browser's trip to
//   accounts.google.com is intercepted by the spec, which registers the code with POST /__codes
// - ID tokens are RS256-signed with a key served at /certs, so the backend's real verification runs
// - PKCE is checked: the token request's code_verifier must match the authorize request's challenge
// - POST /__mail delivers an email to a mailbox; GET /__revoked lists mailboxes whose grant was revoked
import crypto from "node:crypto";
import http from "node:http";

const PORT = Number(process.env.FAKE_GOOGLE_PORT ?? 4518);
const CLIENT_ID = "123-e2e.apps.googleusercontent.com";
const GMAIL = "https://www.googleapis.com/auth/gmail.readonly";
const { privateKey, publicKey } = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });
const jwk = { ...publicKey.export({ format: "jwk" }), kid: "e2e", alg: "RS256", use: "sig" };

const b64 = (data) => Buffer.from(data).toString("base64url");
const codes = new Map();    // code -> { email, nonce, challenge, scope }
const tokens = new Map();   // access or refresh token -> email
const mailboxes = new Map(); // email -> [{ id, from, subject, body, internalDate }]
const revoked = [];

function idToken(email, nonce, accessToken) {
  const now = Math.floor(Date.now() / 1000);
  const half = crypto.createHash("sha256").update(accessToken).digest().subarray(0, 16);
  const claims = { iss: "https://accounts.google.com", aud: CLIENT_ID, sub: String(100000 + email.length) + email.split("@")[0].replace(/\D/g, ""),
    email, email_verified: true, nonce, iat: now, exp: now + 3600, at_hash: b64(half) };
  const signing = `${b64(JSON.stringify({ alg: "RS256", kid: "e2e", typ: "JWT" }))}.${b64(JSON.stringify(claims))}`;
  return `${signing}.${b64(crypto.sign("sha256", Buffer.from(signing), privateKey))}`;
}

function grant(email, scope, nonce) {
  const access = `at-${crypto.randomUUID()}`, refresh = `rt-${crypto.randomUUID()}`;
  tokens.set(access, email).set(refresh, email);
  // A short lifetime, so the worker's first use refreshes it.
  return { access_token: access, refresh_token: refresh, expires_in: 60, token_type: "Bearer", scope,
    ...(nonce !== undefined ? { id_token: idToken(email, nonce, access) } : {}) };
}

function reply(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function gmailMessage(m) {
  const part = (mimeType, text) => ({ mimeType, filename: "", body: { data: b64(text), size: text.length } });
  return { id: m.id, internalDate: String(m.internalDate), payload: {
    mimeType: "multipart/alternative", filename: "",
    headers: [{ name: "From", value: m.from }, { name: "Subject", value: m.subject }],
    parts: [part("text/plain", m.body), part("text/html", `<p>${m.body}</p>`)] } };
}

http.createServer((req, res) => {
  let raw = "";
  req.on("data", c => { raw += c; });
  req.on("end", () => {
    const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
    const form = Object.fromEntries(new URLSearchParams(raw));
    const json = () => JSON.parse(raw || "{}");

    if (req.method === "POST" && url.pathname === "/__codes") {
      const { code, email, nonce, challenge, scope } = json();
      codes.set(code, { email, nonce, challenge, scope: scope ?? `openid https://www.googleapis.com/auth/userinfo.email ${GMAIL}` });
      return reply(res, 200, { ok: true });
    }
    if (req.method === "POST" && url.pathname === "/__mail") {
      const { email, ageSeconds = 0, ...message } = json();
      const list = mailboxes.get(email) ?? [];
      list.push({ ...message, internalDate: Date.now() - ageSeconds * 1000 });
      mailboxes.set(email, list);
      return reply(res, 200, { ok: true });
    }
    if (url.pathname === "/__revoked") return reply(res, 200, revoked);
    if (url.pathname === "/certs") return reply(res, 200, { keys: [jwk] });

    if (req.method === "POST" && url.pathname === "/token") {
      if (form.client_id !== CLIENT_ID || form.client_secret !== "e2e-google-secret") return reply(res, 401, { error: "invalid_client" });
      if (form.grant_type === "authorization_code") {
        const flow = codes.get(form.code);
        codes.delete(form.code);
        const verified = flow && crypto.createHash("sha256").update(form.code_verifier ?? "").digest("base64url") === flow.challenge;
        if (!verified) return reply(res, 400, { error: "invalid_grant" });
        return reply(res, 200, grant(flow.email, flow.scope, flow.nonce));
      }
      if (form.grant_type === "refresh_token" && tokens.has(form.refresh_token)) {
        const { refresh_token: _unused, ...fresh } = grant(tokens.get(form.refresh_token), `openid ${GMAIL}`);
        return reply(res, 200, fresh);
      }
      return reply(res, 400, { error: "invalid_grant" });
    }
    if (req.method === "POST" && url.pathname === "/revoke") {
      const email = tokens.get(form.token);
      if (!email) return reply(res, 400, { error: "invalid_token" });
      for (const [token, owner] of tokens) if (owner === email) tokens.delete(token);
      revoked.push(email);
      return reply(res, 200, {});
    }

    const email = tokens.get((req.headers.authorization ?? "").replace(/^Bearer /, ""));
    if (url.pathname.startsWith("/gmail/v1/users/me/messages")) {
      if (!email) return reply(res, 401, { error: { code: 401 } });
      const list = mailboxes.get(email) ?? [];
      const id = url.pathname.split("/messages/")[1];
      if (id) {
        const found = list.find(m => m.id === decodeURIComponent(id));
        return found ? reply(res, 200, gmailMessage(found)) : reply(res, 404, { error: { code: 404 } });
      }
      const after = Number((url.searchParams.get("q") ?? "").match(/after:(\d+)/)?.[1] ?? 0);
      const inbox = url.searchParams.get("labelIds") === "INBOX" ? list.filter(m => m.internalDate >= after * 1000) : [];
      return reply(res, 200, { messages: inbox.map(m => ({ id: m.id, threadId: m.id })), resultSizeEstimate: inbox.length });
    }
    reply(res, 404, { error: "not found" });
  });
}).listen(PORT, "127.0.0.1");
