import { useEffect, useState } from 'react'
import { api, jsonReq } from '../api.js'

export default function Verify({ token }) {
  const [info, setInfo] = useState(null)
  const [form, setForm] = useState({ amount: '', utr: '', paid_at: '' })
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api(`/v/${token}`).then(setInfo).catch((e) => setErr(e.message))
  }, [token])

  const submit = async () => {
    setBusy(true); setErr('')
    try {
      const body = { amount: form.amount, utr: form.utr || null, paid_at: form.paid_at || null }
      setResult(await api(`/v/${token}/confirm`, jsonReq('POST', body)))
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  if (err && !info) return <div className="card err">{err}</div>
  if (!info) return <div className="card">Loading...</div>

  if (result || info.status === 'confirmed') {
    const rid = result?.record_id || info.record_id
    return (
      <div className="card">
        <h3>Thank you</h3>
        <p>Your confirmation was recorded.</p>
        {rid && <p><a href={`/r/${rid}`}>View the verification record</a></p>}
      </div>
    )
  }
  if (info.expired) return <div className="card">This link has expired. Ask {info.worker_name} for a new one.</div>

  return (
    <div className="card">
      <h3>Confirm a payment</h3>
      <p>
        <b>{info.worker_name}</b> says you paid them via UPI. Enter what <b>you</b> paid, from your own bank or app
        history. You will not be shown their claimed amount.
      </p>
      <label>Amount you paid (Rs) *</label>
      <input value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
      <label>UTR / transaction ID (optional)</label>
      <input value={form.utr} onChange={(e) => setForm({ ...form, utr: e.target.value })} />
      <label>Date and time of payment (optional)</label>
      <input type="datetime-local" value={form.paid_at} onChange={(e) => setForm({ ...form, paid_at: e.target.value })} />
      <button onClick={submit} disabled={busy || !form.amount}>Submit confirmation</button>
      {err && <div className="err">{err}</div>}
    </div>
  )
}
