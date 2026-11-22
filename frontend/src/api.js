export async function api(path, opts = {}) {
  const res = await fetch('/api' + path, opts)
  if (!res.ok) {
    let msg = res.statusText
    try { msg = (await res.json()).detail || msg } catch {}
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json()
}

export const jsonReq = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})