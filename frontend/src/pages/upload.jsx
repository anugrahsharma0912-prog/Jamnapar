import { useEffect, useState } from 'react'
import { api, jsonReq } from '../api.js'

function Findings({ report }) {
  return (
    <div>
      <p>
        Risk score:{' '}
        <b className={`risk-${report.risk_label}`}>{report.risk_score}/100 ({report.risk_label})</b>
      </p>
      {report.findings.length === 0 && <p className="muted">No signs of tampering found. This does not prove the payment is real; the other party's confirmation does.</p>}
      {report.findings.map((f, i) => (
        <div className="finding" key={i}>
          <span className={`sev-${f.severity}`}>[{f.severity}]</span> {f.reason}
        </div>
      ))}
    </div>
  )
}

export default function Upload({ proofId }) {
  const [proof, setProof] = useState(null)
  const [fields, setFields] = useState({})
  const [form, setForm] = useState({ name: '', phone: '', file: null })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')

  const load = (p) => {
    setProof(p)
    const f = p.fields
    setFields({ amount: f.amount || '', utr: f.utr || '', paid_at: f.paid_at || '',
      payer_upi: f.payer_upi || '', payee_upi: f.payee_upi || '', app_name: f.app_name || '' })
  }

  useEffect(() => {
    if (proofId) api(`/proofs/${proofId}`).then(load).catch((e) => setErr(e.message))
  }, [proofId])

  const run = async (fn) => {
    setBusy(true); setErr(''); setNote('')
    try { await fn() } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const upload = () => run(async () => {
    if (!form.file || !form.name || !form.phone) throw new Error('Fill in name, phone and choose a file')
    const fd = new FormData()
    fd.append('file', form.file); fd.append('worker_name', form.name); fd.append('worker_phone', form.phone)
    const p = await api('/proofs', { method: 'POST', body: fd })
    window.history.replaceState({}, '', `/p/${p.id}`)
    load(p)
    if (p.ocr_ok === false) setNote('OCR is not available on this server, so please type the details below.')
    else setNote('We read these values from your file. Check them and fix anything that is wrong.')
  })

  const save = () => run(async () => {
    const body = { ...fields, paid_at: fields.paid_at || null }
    load(await api(`/proofs/${proof.id}/fields`, jsonReq('PATCH', body)))
    setNote('Saved.')
  })

  const makeLink = () => run(async () => {
    await api(`/proofs/${proof.id}/fields`, jsonReq('PATCH', { ...fields, paid_at: fields.paid_at || null })).catch(() => {})
    load(await api(`/proofs/${proof.id}/link`, { method: 'POST' }))
  })

  const refresh = () => run(async () => load(await api(`/proofs/${proof.id}`)))
  const finalize = () => run(async () => {
    await api(`/proofs/${proof.id}/finalize`, { method: 'POST' })
    load(await api(`/proofs/${proof.id}`))
  })

  if (!proof) {
    return (
      <div className="card">
        <h3>Upload a payment proof</h3>
        <p className="muted">Screenshot, PDF receipt, or SMS text file (.txt).</p>
        <label>Your name</label>
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <label>Your phone number</label>
        <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        <label>Proof file</label>
        <input type="file" accept=".png,.jpg,.jpeg,.webp,.pdf,.txt" onChange={(e) => setForm({ ...form, file: e.target.files[0] })} />
        <button onClick={upload} disabled={busy}>{busy ? 'Analyzing...' : 'Upload and analyze'}</button>
        {err && <div className="err">{err}</div>}
      </div>
    )
  }

  const locked = !!proof.link
  const set = (k) => (e) => setFields({ ...fields, [k]: e.target.value })
  const linkUrl = proof.link ? `${window.location.origin}${proof.link.path}` : ''

  return (
    <>
      <div className="card">
        <h3>1. Check the payment details</h3>
        {note && <p className="muted">{note}</p>}
        <div className="row2">
          <div><label>Amount (Rs)</label><input value={fields.amount} onChange={set('amount')} disabled={locked} /></div>
          <div><label>UTR / transaction ID</label><input value={fields.utr} onChange={set('utr')} disabled={locked} /></div>
          <div><label>Date and time</label><input type="datetime-local" value={fields.paid_at} onChange={set('paid_at')} disabled={locked} /></div>
          <div><label>App</label><input value={fields.app_name} onChange={set('app_name')} disabled={locked} /></div>
          <div><label>Payer UPI ID</label><input value={fields.payer_upi} onChange={set('payer_upi')} disabled={locked} /></div>
          <div><label>Payee UPI ID</label><input value={fields.payee_upi} onChange={set('payee_upi')} disabled={locked} /></div>
        </div>
        {!locked && <button className="secondary" onClick={save} disabled={busy}>Save changes</button>}
        {locked && <p className="muted">Locked: your claim cannot change after the link is created.</p>}
        <p className="muted">File SHA-256: <span className="mono">{proof.file_sha256}</span></p>
      </div>

      <div className="card">
        <h3>2. Tamper check</h3>
        <Findings report={proof.report} />
      </div>

      <div className="card">
        <h3>3. Send to the other party</h3>
        {!locked && <button onClick={makeLink} disabled={busy}>Create verification link</button>}
        {locked && (
          <>
            <p>Send this link to the customer or merchant. They will not see your amount.</p>
            <input readOnly value={linkUrl} onFocus={(e) => e.target.select()} />
            <button className="secondary" onClick={() => navigator.clipboard.writeText(linkUrl)}>Copy link</button>
            <p className="muted">
              Status: <b>{proof.link.status}</b>
              {proof.link.opened_at ? ` | opened ${new Date(proof.link.opened_at).toLocaleString()}` : ' | not opened yet'}
            </p>
            <button className="secondary" onClick={refresh} disabled={busy}>Refresh</button>
            {proof.link.status !== 'confirmed' && !proof.records.some((r) => r.verdict === 'unconfirmed') && (
              <button className="secondary" onClick={finalize} disabled={busy}>Close without confirmation</button>
            )}
          </>
        )}
      </div>

      {proof.records.length > 0 && (
        <div className="card">
          <h3>4. Evidence records</h3>
          {proof.records.map((r) => (
            <p key={r.id}>
              <span className={`badge ${r.verdict}`}>{r.verdict}</span>{' '}
              <a href={`/r/${r.id}`}>{new Date(r.created_at).toLocaleString()}</a>
            </p>
          ))}
        </div>
      )}
      {err && <div className="err">{err}</div>}
    </>
  )
}
