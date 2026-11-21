import { useEffect, useState } from 'react'
import { api } from '../api.js'

const rupees = (p) => (p == null ? '-' : `Rs ${(p / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`)

export default function Record({ id }) {
  const [rec, setRec] = useState(null)
  const [err, setErr] = useState('')
  const [check, setCheck] = useState(null)

  useEffect(() => {
    api(`/r/${id}`).then(setRec).catch((e) => setErr(e.message))
  }, [id])

  const verifyFile = async (e) => {
    const fd = new FormData()
    fd.append('file', e.target.files[0])
    setCheck(await api('/verify-file', { method: 'POST', body: fd }))
  }

  if (err) return <div className="card err">{err}</div>
  if (!rec) return <div className="card">Loading...</div>
  const p = rec.payload
  const diff = p.diff || {}
  const cell = (k, fmt = (x) => x) => (
    <tr key={k}>
      <td>{{ amount_paise: 'Amount', utr: 'UTR', paid_at: 'Paid at' }[k]}</td>
      <td>{diff[k]?.claimed == null ? '-' : fmt(diff[k].claimed)}</td>
      <td>{diff[k]?.confirmed == null ? '-' : fmt(diff[k].confirmed)}</td>
      <td>{(diff[k]?.result || 'not compared').replace('_', ' ')}</td>
    </tr>
  )

  return (
    <>
      <div className="card">
        <h3>Verification record</h3>
        <p><span className={`badge ${rec.verdict}`}>{rec.verdict}</span></p>
        <p className="muted">
          Worker: {p.proof.worker_name} ({p.proof.worker_phone_masked}) | Created (UTC): {rec.created_at}
        </p>
        {rec.verdict === 'unconfirmed' && (
          <p>The other party did not confirm. {p.link?.opened_at ? `They opened the link at ${p.link.opened_at}.` : 'The link was never opened.'}</p>
        )}
        {rec.verdict !== 'unconfirmed' && (
          <table>
            <thead><tr><th>Field</th><th>Worker's claim</th><th>Other party</th><th>Result</th></tr></thead>
            <tbody>
              {cell('amount_paise', rupees)}
              {cell('utr')}
              {cell('paid_at', (v) => v.replace('T', ' '))}
            </tbody>
          </table>
        )}
        <p><a href={`/api/r/${rec.record_id}/pdf`}>Download evidence PDF</a></p>
      </div>

      <div className="card">
        <h3>Tamper check</h3>
        <p>Risk score: <b className={`risk-${p.forensics.risk_label}`}>{p.forensics.risk_score}/100 ({p.forensics.risk_label})</b></p>
        {p.forensics.findings.length === 0 && <p className="muted">No findings.</p>}
        {p.forensics.findings.map((f, i) => (
          <div className="finding" key={i}><span className={`sev-${f.severity}`}>[{f.severity}]</span> {f.reason}</div>
        ))}
      </div>

      <div className="card">
        <h3>Integrity</h3>
        <p>Chain status: <b>{rec.chain_valid ? 'intact' : 'BROKEN'}</b></p>
        <p className="muted">Original file SHA-256</p><div className="mono">{p.proof.file_sha256}</div>
        <p className="muted">Previous record hash</p><div className="mono">{rec.prev_hash}</div>
        <p className="muted">This record hash</p><div className="mono">{rec.record_hash}</div>
        <p className="muted">PDF SHA-256</p><div className="mono">{rec.pdf_sha256}</div>
        <p className="muted">Server signature</p><div className="mono">{rec.signature}</div>
        <hr />
        <p>Check a PDF you were given:</p>
        <input type="file" accept=".pdf" onChange={verifyFile} />
        {check && <p><b>{check.authentic ? 'This PDF is exactly the record we issued.' : 'This PDF does NOT match any record we issued.'}</b></p>}
        <p className="muted">
          This shows consistency between two parties' statements and image-integrity signals. It does not confirm the
          payment with a bank or NPCI.
        </p>
      </div>
    </>
  )
}
