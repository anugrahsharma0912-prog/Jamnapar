import Upload from './pages/Upload.jsx'
import Verify from './pages/Verify.jsx'
import Record from './pages/Record.jsx'

// Tiny path router, no extra dependency:
//   /            worker uploads a proof
//   /p/:id       worker's proof page
//   /v/:token    counterparty blind-confirm page
//   /r/:id       public evidence record
export default function App() {
  const parts = window.location.pathname.split('/').filter(Boolean)
  let page
  if (parts[0] === 'v' && parts[1]) page = <Verify token={parts[1]} />
  else if (parts[0] === 'r' && parts[1]) page = <Record id={parts[1]} />
  else page = <Upload proofId={parts[0] === 'p' ? parts[1] : null} />

  return (
    <div className="wrap">
      <header>
        <a href="/"><b>Jamnapar</b></a>
        <span className="muted"> UPI payment proof verification</span>
      </header>
      {page}
    </div>
  )
}
