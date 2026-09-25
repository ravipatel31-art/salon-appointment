/* ══════════════════════════════════════════════════════════════
   Salon Admin Panel (phase 13 + 14 + 15) — vanilla JS, no build, no CDN.
   Auth: POST /auth/login → access_token in sessionStorage (admin only).
   APIs: existing /admin/* endpoints only (docs/CONTRACT.md §Admin).
   Routing (phase 15): client-side PATH router (history.pushState /
   popstate) — real URLs, no hash fragments:
     /panel                 → redirect login page or dashboard
     /panel/login           → login page only (no tabs / no shell)
     /panel/dashboard       → post-login landing
     /panel/barbers | /panel/barbers/new | /panel/barbers/{id}/edit
     /panel/services | /panel/services/new | /panel/services/{id}/edit
     /panel/bookings
   Editors are dedicated full-page views (Back returns to the list);
   destructive Delete + final_price_at_center stay modal.
   Times displayed in Asia/Kolkata; amounts in ₹ (rupees, per contract).
   Security: every dynamic HTML fragment goes through esc(); no eval.
   ══════════════════════════════════════════════════════════════ */
"use strict";

/* ─────────────────────────── helpers ─────────────────────────── */

const TOKEN_KEY = "panel_access_token";
const USER_KEY = "panel_user";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** HTML-escape untrusted text before injecting via innerHTML. */
function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** ₹ + Indian digit grouping (rupees — contract display unit). */
function rupees(n) {
  const v = Number(n || 0);
  return "₹" + v.toLocaleString("en-IN");
}

/** RFC3339 UTC → "24 Sep 2026, 10:30 AM" in Asia/Kolkata. */
function ist(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit", month: "short", year: "numeric",
      hour: "numeric", minute: "2-digit", hour12: true,
    });
  } catch {
    return iso;
  }
}

/** Today's calendar date in Asia/Kolkata (YYYY-MM-DD). */
function todayIST() {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

function toast(msg, isErr = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", isErr);
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 3200);
}

function openModal(id) { $("#" + id).hidden = false; }
function closeModal(id) { $("#" + id).hidden = true; }

/* ─────────────────────────── session ─────────────────────────── */

function getToken() { return sessionStorage.getItem(TOKEN_KEY); }
function getUser() {
  try { return JSON.parse(sessionStorage.getItem(USER_KEY) || "null"); }
  catch { return null; }
}
function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}
function saveSession(token, user) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
}

function showLogin(message = "") {
  $("#shell-view").hidden = true;
  $("#login-view").hidden = false;
  const err = $("#login-error");
  err.textContent = message;
  err.hidden = !message;
}
function showShell(user) {
  $("#login-view").hidden = true;
  $("#shell-view").hidden = false;
  $("#whoami").textContent = user?.name || user?.email || "Admin";
}

/* ─────────────────────────── API client ─────────────────────────── */

class ApiError extends Error {
  constructor(status, detail) { super(detail || `HTTP ${status}`); this.status = status; }
}

/**
 * Fetch JSON with Bearer token. 401 → back to the login page; 403 →
 * surface "admin only" (contract: non-admin token must show admin-only
 * messaging). Both clear the session and land on /panel/login (phase 15).
 */
async function api(path, { method = "GET", body, raw = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let resp;
  try {
    resp = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error");
  }

  if (resp.status === 401) {
    redirectLogin("Session expired — please sign in again.");
    throw new ApiError(401, "unauthorized");
  }
  if (resp.status === 403) {
    redirectLogin("Admin only — this account can’t access the panel.");
    toast("403 · Admin only", true);
    throw new ApiError(403, "admin_only");
  }

  if (resp.status === 204) return null;

  let data = null;
  const text = await resp.text();
  if (text) { try { data = JSON.parse(text); } catch { data = text; } }

  if (!resp.ok) {
    const detail =
      (data && typeof data === "object" && data.detail) || `HTTP ${resp.status}`;
    throw new ApiError(resp.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return raw ? data : data;
}

/* ═══════════════════════ PATH ROUTER (phase 15) ═══════════════════════
   /panel                 → client redirect (session → dashboard, else login)
   /panel/login           → login page only (no tabs / no shell)
   /panel/dashboard       → post-login landing (aggregates)
   /panel/barbers         → list
   /panel/barbers/new · /panel/barbers/{id}/edit → full-page editors
   /panel/services · /panel/services/new · /panel/services/{id}/edit
   /panel/bookings        → list
   Real URLs via history.pushState / popstate — no hash fragments.
   Deep links are served by the existing server SPA fallback
   (GET /panel/{path} → index.html for file-less paths); actual assets
   (/panel/app.js, /panel/app.css) keep resolving as real files.
   ═══════════════════════════════════════════════════════════════════ */

const PANEL_BASE = "/panel";
const LOGIN_PATH = "/panel/login";
const DASH_PATH = "/panel/dashboard";
const TAB_ROOTS = ["barbers", "services", "bookings", "dashboard"];

/** Segments after "/panel" for the current pathname ([] when at /panel). */
function routeParts() {
  let p = location.pathname;
  if (p === PANEL_BASE || p === PANEL_BASE + "/") return [];
  if (p.startsWith(PANEL_BASE + "/")) p = p.slice(PANEL_BASE.length + 1);
  else p = p.replace(/^\/+/, "");
  return p.split("/").filter(Boolean);
}

/** Client-side navigation (history.pushState) → re-render in place. */
function go(path) {
  if (location.pathname === path) applyRoute();
  else {
    history.pushState(null, "", path);
    applyRoute();
  }
}

/** Client-side redirect (history.replaceState) → re-render in place. */
function redirect(path) {
  if (location.pathname === path) applyRoute();
  else {
    history.replaceState(null, "", path);
    applyRoute();
  }
}

/** One-shot message shown on the login page after a redirect. */
let pendingLoginMsg = "";

/** Clear the session and land on /panel/login (401 / 403 / log out). */
function redirectLogin(message = "") {
  clearSession();
  if (location.pathname === LOGIN_PATH) return; // already the login page
  pendingLoginMsg = message;
  redirect(LOGIN_PATH);
}

/** Show exactly one section inside <main class="content">. */
function showOnly(panelId) {
  $$(".content > .panel").forEach((p) => {
    const on = p.id === panelId;
    p.classList.toggle("active", on);
    p.hidden = !on;
  });
}

function setActiveTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
}

async function applyRoute() {
  const parts = routeParts();

  /* ---- /panel → login page or dashboard (client redirect) ---- */
  if (parts.length === 0) {
    redirect(getToken() ? DASH_PATH : LOGIN_PATH);
    return;
  }

  /* ---- /panel/login → login page only (no tabs, no shell) ---- */
  if (parts[0] === "login") {
    const msg = pendingLoginMsg;
    pendingLoginMsg = "";
    showLogin(msg);
    window.scrollTo(0, 0);
    return;
  }

  /* ---- protected paths need a session ---- */
  if (!getToken()) {
    redirectLogin();
    return;
  }

  const root = parts[0];
  const rest = parts.slice(1);
  showShell(getUser());

  /* ---- tab roots ---- */
  if (TAB_ROOTS.includes(root) && rest.length === 0) {
    setActiveTab(root);
    showOnly("tab-" + root);
    window.scrollTo(0, 0);
    if (root === "barbers") loadBarbers();
    if (root === "services") loadServices();
    if (root === "bookings") loadBookings();
    if (root === "dashboard") loadDashboard();
    return;
  }

  /* ---- barber editors ---- */
  if (root === "barbers" && rest.length === 1 && rest[0] === "new") {
    setActiveTab("barbers");
    showOnly("page-barber-edit");
    await openBarberPage(null);
    return;
  }
  if (root === "barbers" && rest.length === 2 && /^\d+$/.test(rest[0]) && rest[1] === "edit") {
    setActiveTab("barbers");
    showOnly("page-barber-edit");
    await openBarberPage(Number(rest[0]));
    return;
  }

  /* ---- service editors ---- */
  if (root === "services" && rest.length === 1 && rest[0] === "new") {
    setActiveTab("services");
    showOnly("page-service-edit");
    openServicePage(null);
    return;
  }
  if (root === "services" && rest.length === 2 && /^\d+$/.test(rest[0]) && rest[1] === "edit") {
    setActiveTab("services");
    showOnly("page-service-edit");
    openServicePage(Number(rest[0]));
    return;
  }

  /* ---- unknown protected path → dashboard ---- */
  if (location.pathname !== DASH_PATH) redirect(DASH_PATH);
}

window.addEventListener("popstate", applyRoute);

/* Back / Cancel controls on the full-page editors */
$$("[data-back]").forEach((btn) =>
  btn.addEventListener("click", () => go("/panel/" + btn.dataset.back))
);

/* ─────────────────────────── boot / login ─────────────────────────── */

async function boot() {
  /* /panel/login → the login page, on its own; no session work needed */
  if (routeParts()[0] === "login") {
    showLogin();
    return;
  }

  /* /panel (no session) and protected deep links (e.g.
     /panel/barbers/1/edit) without a token → the login page */
  if (!getToken()) {
    redirect(LOGIN_PATH);
    return;
  }

  try {
    const me = await api("/auth/me");
    const user = me.user || me;
    if (user.role !== "admin") {
      redirectLogin("Admin only — customer accounts can’t open the panel.");
      return;
    }
    saveSession(getToken(), user);
    // Session restored → render the deep-linked route;
    // at /panel applyRoute redirects to /panel/dashboard.
    await applyRoute();
  } catch (err) {
    if (err.status !== 401 && err.status !== 403) {
      pendingLoginMsg = "Couldn’t verify your session — please sign in again.";
      redirect(LOGIN_PATH);
    }
    // 401/403 already cleared the session and moved to /panel/login.
  }
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#login-submit");
  const errEl = $("#login-error");
  errEl.hidden = true;
  btn.disabled = true;
  btn.textContent = "Signing in…";
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: {
        email: $("#login-email").value.trim(),
        password: $("#login-password").value,
      },
    });
    if (!data.user || data.user.role !== "admin") {
      // Non-admin token → never store; surface as admin-only.
      errEl.textContent = "Admin only — this account can’t access the panel.";
      errEl.hidden = false;
      return;
    }
    saveSession(data.access_token, data.user);
    errEl.hidden = true;
    toast(`Welcome, ${data.user.name || "admin"}`);
    // Contract phase 15: sign-in always lands on the dashboard page.
    redirect(DASH_PATH);
  } catch (err) {
    if (err.status === 401) {
      errEl.textContent = "Invalid email or password.";
    } else if (err.status === 403) {
      errEl.textContent = "Admin only — this account can’t access the panel.";
    } else {
      errEl.textContent = "Sign-in failed — check the API is running.";
    }
    errEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Sign in";
  }
});

$("#logout-btn").addEventListener("click", () => {
  // Contract phase 15: log out → the login page.
  clearSession();
  pendingLoginMsg = "Signed out.";
  redirect(LOGIN_PATH);
});

/* ─────────────────────────── tabs → path routes ─────────────────────────── */

$("#tab-nav").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab");
  if (!btn) return;
  go("/panel/" + btn.dataset.tab);
});

/* modal close buttons (destructive / final-price modals only) */
$$("[data-close]").forEach((btn) =>
  btn.addEventListener("click", () => closeModal(btn.dataset.close))
);
$$(".modal-backdrop").forEach((bd) =>
  bd.addEventListener("click", (e) => { if (e.target === bd) bd.hidden = true; })
);

/* ═════════════════════════ BARBERS ═════════════════════════ */

let barbersCache = [];

async function loadBarbers() {
  try {
    const data = await api("/admin/barbers");
    barbersCache = data.items || [];
    renderBarbers();
    renderBarberFilter();
  } catch (err) {
    if (err.status !== 401 && err.status !== 403) toast("Couldn’t load barbers", true);
  }
}

function initials(name) {
  return String(name || "?")
    .split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase();
}

function renderBarbers() {
  const tbody = $("#barbers-tbody");
  const empty = $("#barbers-empty");
  tbody.innerHTML = "";
  empty.hidden = barbersCache.length > 0;
  for (const b of barbersCache) {
    // Photo fallback is attached from JS (no inline handlers — CSP safe).
    const photo = b.photo_url
      ? `<img class="avatar" src="${esc(b.photo_url)}" alt=""
             data-fallback="${esc(initials(b.name))}" />`
      : `<span class="avatar">${esc(initials(b.name))}</span>`;
    const chips = (b.specialties || [])
      .map((s) => `<span class="chip gold">${esc(s)}</span>`).join("") || "—";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${photo}</td>
      <td><span class="strong">${esc(b.name)}</span>
          <span class="sub">${b.photo_url ? "photo set" : "no photo"}</span></td>
      <td>${esc(b.bio || "—")}</td>
      <td>${chips}</td>
      <td><span class="badge ${b.is_active ? "on" : "off"}">
            ${b.is_active ? "active" : "inactive"}</span></td>
      <td class="col-actions"><div class="row-actions">
        <button class="btn btn-sm btn-ghost" data-act="edit">Edit</button>
        <button class="btn btn-sm btn-danger" data-act="delete">Delete</button>
      </div></td>`;
    // Full-page editor — no scroll-to-edit (phase 14).
    tr.querySelector('[data-act="edit"]').onclick = () =>
      go(`/panel/barbers/${b.id}/edit`);
    tr.querySelector('[data-act="delete"]').onclick = async () => {
      if (!confirm(`Delete barber “${b.name}”? This can’t be undone.`)) return;
      try {
        await api(`/admin/barbers/${b.id}`, { method: "DELETE" });
        toast("Barber deleted");
        await loadBarbers();
      } catch (err) {
        toast(err.status === 409 ? "Barber has bookings — deactivate instead" :
              `Delete failed: ${err.message}`, true);
      }
    };
    tbody.appendChild(tr);
  }
  wireAvatarFallbacks(tbody);
}

/** Replace broken portraits with initials (CSP: no inline onerror). */
function wireAvatarFallbacks(root) {
  $$('img.avatar[data-fallback]', root).forEach((img) => {
    const swap = () => {
      const span = document.createElement("span");
      span.className = "avatar";
      span.textContent = img.dataset.fallback || "?";
      img.replaceWith(span);
    };
    img.addEventListener("error", swap, { once: true });
    if (img.complete && img.naturalWidth === 0) swap();
  });
}

function renderBarberFilter() {
  const sel = $("#bk-barber");
  const current = sel.value;
  sel.innerHTML = `<option value="">All barbers</option>` +
    barbersCache.map((b) =>
      `<option value="${b.id}">${esc(b.name)}</option>`).join("");
  sel.value = current;
}

$("#barber-new-btn").addEventListener("click", () => go("/panel/barbers/new"));

/* ─── full-page barber editor (/panel/barbers/new | /{id}/edit) ─── */

function fillBarberForm(barber) {
  $("#barber-id").value = barber ? barber.id : "";
  $("#barber-name").value = barber?.name || "";
  $("#barber-photo").value = barber?.photo_url || "";
  $("#barber-bio").value = barber?.bio || "";
  $("#barber-specialties").value = (barber?.specialties || []).join(", ");
  $("#barber-active").checked = barber ? !!barber.is_active : true;
  $("#barber-form-error").hidden = true;
  updatePhotoPreview();
}

async function openBarberPage(id) {
  const isNew = id == null;
  $("#schedule-form-error").hidden = true;
  $("#schedule-barber-id").value = isNew ? "" : String(id);

  if (isNew) {
    fillBarberForm(null);
    $("#barber-page-title").textContent = "New barber";
    $("#barber-page-sub").textContent =
      "Create the barber, then set the weekly hours below — both on this page.";
    renderScheduleRows(null);
    window.scrollTo(0, 0);
    $("#barber-name").focus();
    return;
  }

  $("#barber-page-title").textContent = "Edit barber";
  $("#barber-page-sub").textContent = "Details and weekly working hours — one page.";
  renderScheduleRows(null); // skeleton while loading

  let barber = null;
  try {
    const data = await api("/admin/barbers");
    barbersCache = data.items || [];
    renderBarbers();
    renderBarberFilter();
    barber = barbersCache.find((b) => b.id === id) || null;
  } catch (err) {
    if (err.status === 401 || err.status === 403) return;
    toast("Couldn’t load barber", true);
  }
  if (!barber) {
    toast("Barber not found", true);
    go("/panel/barbers");
    return;
  }

  fillBarberForm(barber);
  $("#barber-page-title").textContent = `Edit — ${barber.name}`;
  $("#barber-page-sub").textContent =
    `Barber #${barber.id} · details above, weekly hours alongside.`;

  try {
    const rows = await api(`/admin/barbers/${id}/schedule`);
    renderScheduleRows(rows);
  } catch (err) {
    if (err.status !== 401 && err.status !== 403) {
      toast(`Couldn’t load schedule: ${err.message}`, true);
    }
  }
  window.scrollTo(0, 0);
  $("#barber-name").focus();
}

function updatePhotoPreview() {
  const url = $("#barber-photo").value.trim();
  const box = $("#barber-photo-preview");
  if (!url) { box.hidden = true; return; }
  box.hidden = false;
  $("#barber-photo-img").src = url;
  $("#barber-photo-img").onerror = () => { box.hidden = true; };
}

$("#barber-photo").addEventListener("input", updatePhotoPreview);

$("#barber-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("#barber-id").value;
  const errEl = $("#barber-form-error");
  errEl.hidden = true;
  const specialties = $("#barber-specialties").value
    .split(",").map((s) => s.trim()).filter(Boolean);
  const payload = {
    name: $("#barber-name").value.trim(),
    photo_url: $("#barber-photo").value.trim() || null,
    bio: $("#barber-bio").value.trim(),
    specialties,
    is_active: $("#barber-active").checked,
  };
  try {
    if (id) {
      await api(`/admin/barbers/${id}`, { method: "PATCH", body: payload });
      toast("Barber updated");
      await loadBarbers();
      $("#barber-page-title").textContent = `Edit — ${payload.name}`;
      return;
    }
    // New: create first, then save the schedule from the same page.
    const sched = collectSchedule();
    if (sched.error) return showScheduleError(sched.error);
    const created = await api("/admin/barbers", { method: "POST", body: payload });
    try {
      await api(`/admin/barbers/${created.id}/schedule`, {
        method: "PUT", body: sched.rows,
      });
    } catch (serr) {
      toast(`Barber created — schedule not saved: ${serr.message}`, true);
    }
    toast("Barber created");
    await loadBarbers();
    go(`/panel/barbers/${created.id}/edit`);
  } catch (err) {
    errEl.textContent = err.status === 422
      ? "Name must be 1–120 characters."
      : `Save failed: ${err.message}`;
    errEl.hidden = false;
  }
});

/* ─────────────── weekly schedule (same page as barber form) ─────────────── */

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
                  "Friday", "Saturday", "Sunday"];

/** Render 7 rows; `rows` = GET /admin/barbers/{id}/schedule (null → defaults). */
function renderScheduleRows(rows) {
  // Server/seed convention: weekday Monday=0 … Sunday=6 (Python date.weekday()).
  // Missing days fall back to 09:00–21:00 open.
  const byDay = {};
  for (const r of rows || []) byDay[r.weekday] = r;
  const tbody = $("#schedule-tbody");
  tbody.innerHTML = "";
  for (let wd = 0; wd < 7; wd++) {
    const r = byDay[wd] ||
      { weekday: wd, open_time: "09:00", close_time: "21:00", is_closed: false };
    const tr = document.createElement("tr");
    tr.dataset.weekday = String(wd);
    tr.innerHTML = `
      <td>${WEEKDAYS[wd]}</td>
      <td><input type="time" name="open" value="${esc(r.open_time)}" required /></td>
      <td><input type="time" name="close" value="${esc(r.close_time)}" required /></td>
      <td><input type="checkbox" name="closed" ${r.is_closed ? "checked" : ""} /></td>`;
    tbody.appendChild(tr);
  }
}

function showScheduleError(message) {
  const errEl = $("#schedule-form-error");
  errEl.textContent = message;
  errEl.hidden = false;
}

/** Read the on-page schedule rows → {rows} or {error}. */
function collectSchedule() {
  const rows = $$("#schedule-tbody tr").map((tr) => ({
    weekday: Number(tr.dataset.weekday),
    open_time: tr.querySelector('[name="open"]').value,
    close_time: tr.querySelector('[name="close"]').value,
    is_closed: tr.querySelector('[name="closed"]').checked,
  }));
  for (const row of rows) {
    if (!row.open_time || !row.close_time || row.open_time >= row.close_time) {
      return { error: "Each day needs open time earlier than close time." };
    }
  }
  return { rows };
}

$("#schedule-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = $("#schedule-form-error");
  errEl.hidden = true;
  const id = $("#schedule-barber-id").value;
  if (!id) {
    showScheduleError("Save the barber first, then the schedule.");
    return;
  }
  const sched = collectSchedule();
  if (sched.error) return showScheduleError(sched.error);
  try {
    await api(`/admin/barbers/${id}/schedule`, { method: "PUT", body: sched.rows });
    toast("Schedule saved");
  } catch (err) {
    errEl.textContent =
      err.message === "duplicate_weekday" ? "Duplicate day in schedule."
      : err.message === "invalid_hours" ? "Open time must be before close time."
      : `Save failed: ${err.message}`;
    errEl.hidden = false;
  }
});

/* ═════════════════════════ SERVICES ═════════════════════════ */

let servicesCache = [];

async function loadServices() {
  try {
    const data = await api("/admin/services");
    servicesCache = data.items || [];
    renderServices();
  } catch (err) {
    if (err.status !== 401 && err.status !== 403) toast("Couldn’t load services", true);
  }
}

/** service_id → price_type (used to require final price on colour). */
function priceTypeOf(serviceId) {
  const s = servicesCache.find((x) => x.id === serviceId);
  return s ? s.price_type : null;
}

function renderServices() {
  const tbody = $("#services-tbody");
  const empty = $("#services-empty");
  tbody.innerHTML = "";
  empty.hidden = servicesCache.length > 0;
  for (const s of servicesCache) {
    const isVar = s.price_type === "variable_advance";
    const priceLabel = isVar
      ? `${rupees(s.price)} <span class="sub">online advance</span>`
      : rupees(s.price);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="strong">${esc(s.name)}</span></td>
      <td>${esc(s.description || "—")}</td>
      <td class="num">${s.duration_minutes} min</td>
      <td class="num">${priceLabel}</td>
      <td><span class="chip ${isVar ? "wine" : ""}">${isVar ? "variable advance" : "fixed"}</span></td>
      <td><span class="badge ${s.is_active ? "on" : "off"}">
            ${s.is_active ? "active" : "inactive"}</span></td>
      <td class="col-actions"><div class="row-actions">
        <button class="btn btn-sm btn-ghost" data-act="edit">Edit</button>
        <button class="btn btn-sm btn-danger" data-act="delete">Delete</button>
      </div></td>`;
    // Full-page editor (phase 14).
    tr.querySelector('[data-act="edit"]').onclick = () =>
      go(`/panel/services/${s.id}/edit`);
    tr.querySelector('[data-act="delete"]').onclick = async () => {
      if (!confirm(`Delete service “${s.name}”?`)) return;
      try {
        await api(`/admin/services/${s.id}`, { method: "DELETE" });
        toast("Service deleted");
        await loadServices();
      } catch (err) {
        toast(err.status === 409 ? "Service has bookings — deactivate instead"
              : `Delete failed: ${err.message}`, true);
      }
    };
    tbody.appendChild(tr);
  }
}

function syncTypeHint() {
  const isVar = $("#service-price-type").value === "variable_advance";
  $("#service-type-hint").hidden = !isVar;
  if (isVar && $("#service-price-type").dataset.fresh === "1") {
    // Convenience only — admin can still type another online advance value.
    $("#service-price").value = $("#service-price").value || 100;
  }
}
$("#service-price-type").addEventListener("change", syncTypeHint);

$("#service-new-btn").addEventListener("click", () => go("/panel/services/new"));

/* ─── full-page service editor (/panel/services/new | /{id}/edit) ─── */

function openServicePage(id) {
  const isNew = id == null;
  const service = isNew ? null : servicesCache.find((s) => s.id === id) || null;
  $("#service-price-type").dataset.fresh = isNew ? "1" : "0";
  $("#service-page-title").textContent = isNew ? "New service" : "Edit service";
  $("#service-page-sub").textContent = isNew
    ? "Add a salon plan row — price in ₹; hair colour keeps the ₹100 online advance."
    : "Salon plan row — price in ₹, hair colour keeps the ₹100 online advance.";
  $("#service-id").value = service ? service.id : "";
  $("#service-name").value = service?.name || "";
  $("#service-description").value = service?.description || "";
  $("#service-duration").value = service?.duration_minutes || 30;
  $("#service-price").value = service?.price ?? 100;
  $("#service-price-type").value = service?.price_type || "fixed";
  $("#service-active").checked = service ? !!service.is_active : true;
  $("#service-form-error").hidden = true;
  syncTypeHint();
  window.scrollTo(0, 0);
  $("#service-name").focus();
}

$("#service-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("#service-id").value;
  const errEl = $("#service-form-error");
  errEl.hidden = true;
  const payload = {
    name: $("#service-name").value.trim(),
    description: $("#service-description").value.trim(),
    duration_minutes: Number($("#service-duration").value),
    price: Number($("#service-price").value),
    price_type: $("#service-price-type").value,
    is_active: $("#service-active").checked,
  };
  try {
    if (id) {
      await api(`/admin/services/${id}`, { method: "PATCH", body: payload });
      toast("Service updated");
      await loadServices();
      $("#service-page-title").textContent = `Edit — ${payload.name}`;
      return;
    }
    const created = await api("/admin/services", { method: "POST", body: payload });
    toast("Service created");
    await loadServices();
    go(`/panel/services/${created.id}/edit`);
  } catch (err) {
    errEl.textContent =
      err.status === 409 ? "A service with that name already exists."
      : err.status === 422 ? "Check the form: name, positive duration & price."
      : `Save failed: ${err.message}`;
    errEl.hidden = false;
  }
});

/* ═════════════════════════ BOOKINGS ═════════════════════════ */

async function loadBookings() {
  const params = new URLSearchParams();
  const date = $("#bk-date").value;
  const barber = $("#bk-barber").value;
  const status = $("#bk-status").value;
  if (date) params.set("date", date);
  if (barber) params.set("barber_id", barber);
  if (status) params.set("status", status);
  try {
    const data = await api(`/admin/bookings?${params.toString()}`);
    renderBookings(data.items || []);
  } catch (err) {
    if (err.status !== 401 && err.status !== 403) {
      toast(`Couldn’t load bookings: ${err.message}`, true);
    }
  }
}

function renderBookings(items) {
  const tbody = $("#bookings-tbody");
  const empty = $("#bookings-empty");
  tbody.innerHTML = "";
  empty.hidden = items.length > 0;
  for (const b of items) {
    const canAct = b.status === "pending_payment" || b.status === "confirmed";
    const customer = [b.guest_name, b.guest_phone].filter(Boolean).join(" · ") || "—";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="strong">${esc(b.booking_ref)}</span>
          <span class="sub">${b.duration_minutes} min</span></td>
      <td>${esc(ist(b.start_at))}</td>
      <td>${esc(customer)}</td>
      <td>${esc(b.service_name || b.service_id)}</td>
      <td>${esc(b.barber_name || b.barber_id)}</td>
      <td class="num">${rupees(b.total_amount)}</td>
      <td class="num">${rupees(b.online_amount_paid)}
          ${b.balance_due != null ? `<span class="sub">bal. ${rupees(b.balance_due)}</span>` : ""}</td>
      <td><span class="badge ${esc(b.status)}">${esc(b.status.replace("_", " "))}</span></td>
      <td class="col-actions"><div class="row-actions">
        ${canAct ? `<button class="btn btn-sm btn-primary" data-act="complete">Complete</button>
                    <button class="btn btn-sm btn-danger" data-act="no-show">No-show</button>`
                 : `<span class="sub">—</span>`}
      </div></td>`;
    const completeBtn = tr.querySelector('[data-act="complete"]');
    if (completeBtn) completeBtn.onclick = () => openComplete(b);
    const noShowBtn = tr.querySelector('[data-act="no-show"]');
    if (noShowBtn) noShowBtn.onclick = () => markNoShow(b);
    tbody.appendChild(tr);
  }
}

$("#bk-refresh").addEventListener("click", loadBookings);
$("#bk-date").addEventListener("change", loadBookings);
$("#bk-barber").addEventListener("change", loadBookings);
$("#bk-status").addEventListener("change", loadBookings);
$("#bk-clear").addEventListener("click", () => {
  $("#bk-date").value = "";
  $("#bk-barber").value = "";
  $("#bk-status").value = "";
  loadBookings();
});

/* complete — hair colour (variable_advance) requires final_price_at_center */
function openComplete(b) {
  const isVar = priceTypeOf(b.service_id) === "variable_advance";
  $("#complete-booking-id").value = b.id;
  $("#complete-summary").textContent =
    `${b.booking_ref} · ${b.service_name || "service"} · paid online ${rupees(b.online_amount_paid)}`;
  const input = $("#complete-final-price");
  input.required = isVar;
  input.placeholder = isVar ? "Required — e.g. 450" : `Optional (defaults to ${rupees(b.total_amount)})`;
  $("#complete-require-hint").textContent = isVar
    ? "· required for hair colour"
    : "· optional";
  input.value = "";
  $("#complete-form-error").hidden = true;
  openModal("complete-modal");
  input.focus();
}

$("#complete-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("#complete-booking-id").value;
  const raw = $("#complete-final-price").value;
  const body = { action: "complete" };
  if (raw !== "") body.final_price_at_center = Number(raw);
  const errEl = $("#complete-form-error");
  errEl.hidden = true;
  try {
    await api(`/admin/bookings/${id}`, { method: "PATCH", body });
    closeModal("complete-modal");
    toast("Booking completed");
    await Promise.all([loadBookings(), loadDashboard()]);
  } catch (err) {
    if (err.message === "final_price_at_center_required") {
      errEl.textContent = "Final price at centre is required for hair colour.";
    } else if (err.message === "invalid_status") {
      errEl.textContent = "Only pending/confirmed bookings can be completed.";
    } else {
      errEl.textContent = `Failed: ${err.message}`;
    }
    errEl.hidden = false;
  }
});

async function markNoShow(b) {
  if (!confirm(`Mark ${b.booking_ref} as no-show?`)) return;
  try {
    await api(`/admin/bookings/${b.id}`, { method: "PATCH", body: { action: "no_show" } });
    toast("Marked no-show");
    await Promise.all([loadBookings(), loadDashboard()]);
  } catch (err) {
    toast(`Failed: ${err.message}`, true);
  }
}

/* ═════════════════════════ DASHBOARD ═════════════════════════ */

async function loadDashboard() {
  const date = $("#dash-date").value || todayIST();
  $("#dash-date").value = date;
  try {
    const d = await api(`/admin/dashboard?date=${date}`);
    $("#stat-bookings").textContent = d.bookings_count;
    $("#stat-confirmed").textContent = d.confirmed_count;
    $("#stat-online").textContent = rupees(d.revenue_online);
    $("#stat-centre").textContent = rupees(d.revenue_at_center);
    const label = $("#dash-date-label");
    label.textContent = `Aggregates for ${d.date} (Asia/Kolkata day)`;
    label.hidden = false;
  } catch (err) {
    if (err.status !== 401 && err.status !== 403) {
      toast(`Couldn’t load dashboard: ${err.message}`, true);
    }
  }
}

$("#dash-refresh").addEventListener("click", loadDashboard);
$("#dash-date").addEventListener("change", loadDashboard);

/* ─────────────────────────── init ─────────────────────────── */

$("#dash-date").value = todayIST();
boot();
