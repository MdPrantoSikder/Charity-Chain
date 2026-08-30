const API_BASE = (location.hostname.endsWith('.app.github.dev'))
  ? location.origin.replace(/-\d+\.app\.github\.dev$/, '-8000.app.github.dev')
  : 'http://127.0.0.1:8000';

async function apiFetch(endpoint, options = {}) {
  const token = Auth.getToken();

  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {})
  };

  let res;
  try {
    res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
  } catch (err) {
    // Network-level failure: backend down, CORS blocked, wrong port.
    // The old version swallowed this into the same generic message as a 4xx,
    // which made "server not running" look identical to "bad request".
    console.error(`API unreachable [${endpoint}]:`, err.message);
    throw new Error(`Cannot reach the API at ${API_BASE} — is uvicorn running?`);
  }

  if (res.status === 401) {
    Auth.logout();
    return null;
  }

  // 204 No Content and empty bodies would throw on res.json()
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
      return text;
    }
  }

  if (!res.ok) {
    const detail = data?.detail;
    // FastAPI validation errors come back as an ARRAY of objects, not a string.
    // Rendering that array directly printed "[object Object]" to the user --
    // which is exactly what AdmitNodeRequest's ge/le field limits produce.
    const msg = Array.isArray(detail)
      ? detail.map(d => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
      : (detail || `HTTP ${res.status}`);
    throw new Error(msg);
  }

  return data;
}

/* ──────────────────────────────────────────
   AUTH ENDPOINTS
   ────────────────────────────────────────── */

const AuthAPI = {

  async register(data) {
    return apiFetch('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async login(email, password) {
    return apiFetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
  },

  async me() {
    return apiFetch('/api/auth/me');
  }

};

/* ──────────────────────────────────────────
   CASES ENDPOINTS
   ────────────────────────────────────────── */

const CasesAPI = {

  async submit(formData) {
    const token = Auth.getToken();
    // NOTE: no Content-Type header here on purpose — the browser must set the
    // multipart boundary itself, so this call cannot go through apiFetch.
    const res = await fetch(`${API_BASE}/api/cases/submit`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Case submission failed');
    }
    return res.json();
  },

  async getPending() {
    return apiFetch('/api/cases/pending');
  },

  async getApproved() {
    return apiFetch('/api/cases/approved');
  },

  async getById(id) {
    return apiFetch(`/api/cases/${id}`);
  },

  async getMyCases() {
    return apiFetch('/api/cases/my');
  },

  async approve(id, notes) {
    return apiFetch(`/api/cases/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ notes })
    });
  },

  async reject(id, reason) {
    return apiFetch(`/api/cases/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    });
  },

  async getDocuments(caseId) {
    return apiFetch(`/api/cases/${caseId}/documents`);
  },

  async getDocumentViewUrl(docId) {
    return `${API_BASE}/api/cases/documents/${docId}/view`;
  }

};

/* ──────────────────────────────────────────
   DONATIONS ENDPOINTS
   ────────────────────────────────────────── */

const DonationsAPI = {

  async donate(caseId, amount) {
    return apiFetch('/api/donations/donate', {
      method: 'POST',
      body: JSON.stringify({ case_id: caseId, amount })
    });
  },

  async track(donationId) {
    return apiFetch(`/api/donations/track/${donationId}`);
  },

  async getMyDonations() {
    return apiFetch('/api/donations/my');
  }

};

/* ──────────────────────────────────────────
   PAYMENT ENDPOINTS (SSLCommerz)
   ────────────────────────────────────────── */

const PaymentAPI = {

  async initiate(amount) {
    return apiFetch('/api/payment/initiate', {
      method: 'POST',
      body: JSON.stringify({ amount })
    });
  }

};

/* ──────────────────────────────────────────
   BLOCKCHAIN ENDPOINTS
   ────────────────────────────────────────── */

const BlockchainAPI = {

  async getChain() {
    return apiFetch('/api/chain');
  },

  async getBlock(id) {
    return apiFetch(`/api/chain/${id}`);
  },

  async getAuditLog() {
    return apiFetch('/api/transparency/audit');
  },

  async getConsensusLogs() {
    return apiFetch('/api/transparency/consensus-logs');
  },

  /* Chain node status — client version, chain id, current height.
     Proves whether blocks are really reaching Besu/Hardhat. */
  async getStatus() {
    return apiFetch('/api/blockchain/status');
  }

};

/* ──────────────────────────────────────────
   ADMIN ENDPOINTS
   ────────────────────────────────────────── */

const AdminAPI = {

  async getNodes() {
    return apiFetch('/api/nodes');
  },

  async getNode(id) {
    return apiFetch(`/api/nodes/${id}`);
  },

  async getEpoch() {
    return apiFetch('/api/consensus/epoch');
  },

  /* Which consensus is live (CB-BFT / Raft / PBFT), the CRITIC weights it
     computed this epoch, cluster counts and Byzantine tolerance. Drives the
     consensus pill and the weights panel on the admin dashboard. */
  async getConsensusInfo() {
    return apiFetch('/api/consensus/info');
  },

  /* Force a re-score and re-cluster now. Backs the "Recluster Now" button on
     the JSD drift banner — which previously only ran a setTimeout and showed
     a success toast without reclustering anything. */
  async recluster() {
    return apiFetch('/api/admin/recluster', { method: 'POST' });
  },

  async admitNode(data) {
    return apiFetch('/api/admin/admit-node', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },

  async getUsers() {
    return apiFetch('/api/admin/users');
  },

  async getPendingTrustees() {
    return apiFetch('/api/admin/trustees/pending');
  },

  async approveTrustee(userId) {
    return apiFetch(`/api/admin/trustees/${userId}/approve`, {
      method: 'POST'
    });
  },

  async rejectTrustee(userId) {
    return apiFetch(`/api/admin/trustees/${userId}/reject`, {
      method: 'POST'
    });
  },

  async topUp(userId, amount) {
    return apiFetch(`/api/admin/topup/${userId}`, {
      method: 'POST',
      body: JSON.stringify({ amount })
    });
  }

};

/* ──────────────────────────────────────────
   HELPERS
   ────────────────────────────────────────── */

function openIPFS(cid) {
  if (!cid) {
    Toast.show('No document uploaded for this case', 'warning');
    return;
  }
  window.open(`https://ipfs.io/ipfs/${cid}`, '_blank');
}