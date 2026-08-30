/* ============================================================
   auth.js — JWT token management
   Handles: save token, read token, get user info, logout
   Used by: ALL pages
   ============================================================ */

const Auth = {

  // ── Save token after login ──
  // Called by index.html after successful login API response
  setToken(token) {
    localStorage.setItem('cc_token', token);
  },

  // ── Get token for API calls ──
  // Every fetch() call uses this in the Authorization header
  getToken() {
    return localStorage.getItem('cc_token');
  },

  // ── Save user info ──
  // Called after login — stores name, role, email
  setUser(user) {
    localStorage.setItem('cc_user', JSON.stringify(user));
  },

  // ── Get user info ──
  // Used to show "Welcome back, John" and check role
  getUser() {
    const u = localStorage.getItem('cc_user');
    return u ? JSON.parse(u) : null;
  },

  // ── Check if logged in ──
  // Every dashboard page calls this on load
  // If not logged in → redirect to login page
  isLoggedIn() {
    return !!this.getToken();
  },

  // ── Get user role ──
  // Used to protect pages — donor cant access admin page
  getRole() {
    const user = this.getUser();
    return user ? user.role : null;
  },

  // ── Protect a page by role ──
  // Call this at the top of every dashboard page
  // Example: Auth.requireRole('donor') on donor.html
  requireRole(role) {
    if (!this.isLoggedIn()) {
      window.location.href = 'index.html';
      return false;
    }
    if (role && this.getRole() !== role) {
      // Wrong role — send to their correct dashboard
      this.redirectToDashboard();
      return false;
    }
    return true;
  },

  // ── Redirect user to their correct dashboard ──
  // After login — each role has its own page
  redirectToDashboard() {
    const role = this.getRole();
    const routes = {
      donor:     'donor.html',
      needy:     'needy.html',
      trustee:   'trustee.html',
      admin:     'admin.html',
      validator: 'admin.html'
    };
    window.location.href = routes[role] || 'index.html';
  },

  // ── Logout ──
  // Clears everything and goes back to login
  logout() {
    localStorage.removeItem('cc_token');
    localStorage.removeItem('cc_user');
    window.location.href = 'index.html';
  },

  // ── Fill in user info on page ──
  // Call this on every dashboard to show name + role in sidebar
  // It looks for elements with these IDs and fills them
  fillUserInfo() {
    const user = this.getUser();
    if (!user) return;

    // Sidebar user name
    const nameEl = document.getElementById('user-name');
    if (nameEl) nameEl.textContent = user.full_name || user.email;

    // Sidebar user role
    const roleEl = document.getElementById('user-role');
    if (roleEl) roleEl.textContent = user.role;

    // Sidebar avatar initials
    const avatarEl = document.getElementById('user-avatar');
    if (avatarEl) {
      const name = user.full_name || user.email || '?';
      avatarEl.textContent = name.charAt(0).toUpperCase();
    }

    // Topbar welcome message
    const welcomeEl = document.getElementById('welcome-name');
    if (welcomeEl) {
      const first = (user.full_name || user.email).split(' ')[0];
      welcomeEl.textContent = first;
    }
  }

};