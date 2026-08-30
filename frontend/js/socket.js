/* ============================================================
   socket.js — WebSocket connection for live ABPC updates
   Listens to real-time events from FastAPI backend
   Used by: donor.html (consensus pipeline) 
            admin.html (JSD drift alerts)
   ============================================================ */

// ── WebSocket URL ──
// Change this when you deploy to Render
const WS_BASE = 'ws://localhost:8000';

const Socket = {

  ws: null,         // the WebSocket connection
  listeners: {},    // event name → callback function

  // ── Connect to backend WebSocket ──
  connect(donationId = null) {
    // If already connected, close first
    if (this.ws) this.ws.close();

    // Connect — pass donation ID so backend knows which
    // consensus pipeline to stream updates for
    const url = donationId
      ? `${WS_BASE}/ws?donation_id=${donationId}`
      : `${WS_BASE}/ws`;

    this.ws = new WebSocket(url);

    // When connection opens
    this.ws.onopen = () => {
      console.log('🔌 WebSocket connected');
      // Send JWT token to authenticate the socket
      this.ws.send(JSON.stringify({
        type: 'auth',
        token: Auth.getToken()
      }));
    };

    // When a message arrives from backend
    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        console.log('📡 WS Event:', msg.event, msg.data);

        // Fire the matching listener if registered
        if (msg.event && this.listeners[msg.event]) {
          this.listeners[msg.event](msg.data);
        }

        // Always fire wildcard listener if set
        if (this.listeners['*']) {
          this.listeners['*'](msg);
        }

      } catch (err) {
        console.error('WS parse error:', err);
      }
    };

    // When connection closes
    this.ws.onclose = () => {
      console.log('🔌 WebSocket disconnected');
    };

    // On error
    this.ws.onerror = (err) => {
      console.error('WS error:', err);
    };
  },

  // ── Register an event listener ──
  // Usage: Socket.on('block_confirmed', (data) => { ... })
  //
  // These are the events the ABPC backend emits:
  //   pool_formed       → L5 pools created
  //   leader_elected    → L6 VRF winner chosen
  //   bft_vote          → L7 intra-pool vote
  //   block_confirmed   → L8 inter-pool HotStuff passed
  //   funds_released    → money sent to case
  //   jsd_alert         → L9 drift > 0.15 detected
  //   recluster_started → L9 triggered recluster
  //   consensus_failed  → rejected, backup leader trying
  on(eventName, callback) {
    this.listeners[eventName] = callback;
  },

  // ── Remove a listener ──
  off(eventName) {
    delete this.listeners[eventName];
  },

  // ── Disconnect ──
  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.listeners = {};
  }

};

/* ──────────────────────────────────────────
   TOAST HELPER
   Small notification popups — used everywhere
   Usage: Toast.show('Donation confirmed!', 'success')
   ────────────────────────────────────────── */

const Toast = {

  show(message, type = 'info', duration = 3500) {
    // Create container if not exists
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }

    // Create toast
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
      success: '✅',
      error:   '❌',
      warning: '⚠️',
      info:    'ℹ️'
    };

    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span> ${message}`;
    container.appendChild(toast);

    // Auto remove
    setTimeout(() => {
      toast.style.animation = 'toast-out 0.3s ease forwards';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

};

/* ──────────────────────────────────────────
   COPY TO CLIPBOARD HELPER
   Used for block hashes throughout the app
   Usage: copyHash('0x8f71...ac34', element)
   ────────────────────────────────────────── */

function copyHash(hash, element) {
  navigator.clipboard.writeText(hash).then(() => {
    Toast.show('Hash copied to clipboard', 'success', 2000);
    if (element) {
      const original = element.textContent;
      element.textContent = '✅ Copied!';
      element.classList.add('copied');
      setTimeout(() => {
        element.textContent = original;
        element.classList.remove('copied');
      }, 2000);
    }
  });
}