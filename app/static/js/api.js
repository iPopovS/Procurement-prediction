// Thin fetch wrapper: errors become readable messages (never raw JSON / stack traces).
import { translateMessage } from './i18n.js';
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
    this.rawMessage = message;
    Object.defineProperty(this, 'message', { get: () => translateMessage(this.rawMessage) });
  }
}

function toQuery(params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v === null || v === undefined || v === '') continue;
    if (Array.isArray(v)) v.forEach((x) => q.append(k, x));
    else q.append(k, v);
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}

export async function api(path, { method = 'GET', params, body, signal } = {}) {
  let res;
  try {
    res = await fetch(`${path}${toQuery(params)}`, {
      method, signal,
      headers: body ? { 'Content-Type': 'application/json', Accept: 'application/json' } : { Accept: 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError('Cannot reach the server. Check your connection and try again.', 0);
  }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON body */ }
  if (!res.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map((m) => m.msg).join('; ');
    throw new ApiError(msg || `The server answered with an error (HTTP ${res.status}).`, res.status);
  }
  return data;
}
