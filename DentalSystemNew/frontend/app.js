const state = {
  user: null,
  csrfToken: "",
  feedback: [],
  services: [],
  promos: [],
  availability: [],
  clinicDoctor: ""
};

const fallbackServices = [
  { name: "Oral Prophylaxis", description: "Routine cleaning and plaque removal for healthier gums." },
  { name: "Tooth Restoration", description: "Fillings and tooth repair for cavities and minor damage." },
  { name: "Tooth Extraction", description: "Assessment and safe tooth removal when needed." },
  { name: "Braces Consultation", description: "Initial orthodontic evaluation and treatment planning." },
  { name: "Root Canal Therapy", description: "Treatment for infected pulp while preserving the tooth." },
  { name: "Teeth Whitening", description: "Cosmetic whitening options for a brighter smile." }
];

const fallbackPromos = [
  { title: "New Patient Starter", description: "Free dental assessment with your first cleaning appointment." },
  { title: "Family Smile Day", description: "Save 15% when three or more family members book checkups." },
  { title: "Whitening Bundle", description: "Consultation plus whitening plan at a reduced package rate." }
];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value) {
  if (!value) return "-";
  const [year, month, day] = value.split("-");
  return `${month}/${day}/${year}`;
}

function dashboardUrl(role) {
  return role === "doctor" ? "doctor-dashboard.html" : "patient-dashboard.html";
}

function queueToast(message, type = "success") {
  sessionStorage.setItem("drms_toast", JSON.stringify({ message, type }));
}

function consumeQueuedToast() {
  const queued = sessionStorage.getItem("drms_toast");
  if (!queued) return;
  sessionStorage.removeItem("drms_toast");
  try {
    const { message, type } = JSON.parse(queued);
    showToast(message, type);
  } catch {
    return;
  }
}

function showToast(message, type = "success") {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = `toast ${type}`;
  toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 3600);
}

function validatedPayload(form) {
  try {
    return window.DRMSSecurity.formPayload(form);
  } catch (error) {
    showToast(error.message, "error");
    return null;
  }
}

async function api(path, options = {}) {
  if (window.location.protocol === "file:") {
    throw new Error("Open the app through the Python server, not by double-clicking index.html. Run python backend/server.py --port 8000, then visit http://127.0.0.1:8000.");
  }

  let response;
  try {
    const method = String(options.method || "GET").toUpperCase();
    const headers = {
      "X-Requested-With": "DentalSystem",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(state.csrfToken && method !== "GET" ? { "X-CSRF-Token": state.csrfToken } : {}),
      ...(options.headers || {})
    };
    response = await fetch(path, {
      ...options,
      method,
      credentials: "same-origin",
      headers
    });
  } catch {
    throw new Error("Cannot reach the server. Make sure server.py is running, then open the app using the local server URL shown in the terminal.");
  }
  const body = await response.json().catch(() => ({}));
  if (body.csrf_token) state.csrfToken = body.csrf_token;
  if (!response.ok) {
    throw new Error(body.error || "Something went wrong.");
  }
  return body;
}

function renderBookingDentists() {
  const input = $("#doctorSelect");
  const scheduledDoctor = state.availability.find((slot) => slot.doctor)?.doctor || "";
  input.value = state.clinicDoctor || scheduledDoctor;
  renderBookingDates();
}

function renderBookingDates() {
  const select = $("#appointmentDate");
  const previous = select.value;
  const doctor = $("#doctorSelect").value;
  const dates = [...new Set(
    state.availability
      .filter((slot) => slot.doctor === doctor && !slot.booked)
      .map((slot) => slot.date)
      .filter(Boolean)
  )].sort();
  select.innerHTML = `<option value="">Select available date</option>${dates.map((date) => (
    `<option value="${escapeHtml(date)}">${formatDate(date)}</option>`
  )).join("")}`;
  select.value = dates.includes(previous) ? previous : dates[0] || "";
  renderTimeSlots();
}

function renderTimeSlots() {
  const wrap = $("#timeSlots");
  const doctor = $("#doctorSelect").value;
  const date = $("#appointmentDate").value;
  const slots = state.availability
    .filter((slot) => slot.doctor === doctor && slot.date === date && !slot.booked)
    .sort((left, right) => left.time.localeCompare(right.time));
  wrap.innerHTML = "";
  $("#selectedTime").value = "";
  $("#selectedTimeLabel").textContent = "Select slot";
  if (!slots.length) {
    wrap.innerHTML = `<p class="availability-empty">${doctor && date
      ? "No open times remain for this date."
      : "The clinic has not opened an appointment slot yet."}</p>`;
    $("#appointmentSubmit").disabled = true;
    return;
  }
  slots.forEach((slot) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "time-slot";
    button.textContent = slot.time;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => {
      wrap.querySelectorAll(".time-slot").forEach((item) => {
        item.classList.remove("active");
        item.setAttribute("aria-pressed", "false");
      });
      button.classList.add("active");
      button.setAttribute("aria-pressed", "true");
      $("#selectedTime").value = slot.time;
      $("#selectedTimeLabel").textContent = slot.time;
    });
    wrap.appendChild(button);
  });
  $("#appointmentSubmit").disabled = false;
}

function resetAppointmentForm() {
  $("#appointmentForm").reset();
  renderBookingDentists();
}

function openAuth(mode = "login") {
  $("#authModal").classList.remove("hidden");
  switchAuthTab(mode);
}

function closeAuth() {
  setLoginPasswordVisible(false);
  $("#authModal").classList.add("hidden");
}

function switchAuthTab(mode) {
  $$("[data-auth-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.authTab === mode);
  });
  $("#loginForm").classList.toggle("hidden", mode !== "login");
  $("#registerForm").classList.toggle("hidden", mode !== "register");
  $("#authModal").setAttribute("aria-labelledby", mode === "login" ? "authTitle" : "registerTitle");
  $("#authModal").setAttribute("aria-describedby", mode === "login" ? "authSubtitle" : "registerSubtitle");
  setTimeout(() => {
    const activeForm = mode === "login" ? $("#loginForm") : $("#registerForm");
    activeForm.querySelector("input, select, button")?.focus();
  }, 0);
}

function setLoginPasswordVisible(isVisible) {
  const input = $("#loginPassword");
  const toggle = $("#passwordToggle");
  input.type = isVisible ? "text" : "password";
  toggle.classList.toggle("is-visible", isVisible);
  toggle.setAttribute("aria-pressed", String(isVisible));
  toggle.setAttribute("aria-label", isVisible ? "Hide password" : "Show password");
}

function updateAuthUI() {
  const loggedIn = Boolean(state.user);
  $("#loginOpen").classList.toggle("hidden", loggedIn);
  $("#registerOpen").classList.toggle("hidden", loggedIn);
  $("#logoutButton").classList.toggle("hidden", !loggedIn);
  $("#dashboardJump").classList.toggle("hidden", !loggedIn);

  if (state.user?.role === "doctor") {
    $("#bookingGateText").textContent = "Doctor accounts manage appointments from the dashboard.";
  } else {
    $("#bookingGateText").textContent = loggedIn
      ? "Your booking will be connected to your patient account."
      : "Browsing is open to everyone. Booking requires a patient account.";
  }

  $("#feedbackName").disabled = loggedIn;
  $("#feedbackName").placeholder = loggedIn ? state.user.name : "Your name";
}

async function loadSession() {
  const data = await api("/api/session");
  state.user = data.user;
  state.csrfToken = data.csrf_token || "";
  updateAuthUI();
}

async function loadServices() {
  try {
    const data = await api("/api/services");
    state.services = data.services.length ? data.services : fallbackServices;
  } catch {
    state.services = fallbackServices;
  }
  renderServices();
}

async function loadAvailability() {
  const data = await api("/api/availability");
  state.availability = data.availability || [];
  state.clinicDoctor = data.clinic_doctor || "";
  renderBookingDentists();
}

async function loadPromos() {
  try {
    const data = await api("/api/promos");
    state.promos = data.promos.length ? data.promos : fallbackPromos;
  } catch {
    state.promos = fallbackPromos;
  }
  renderPromos();
}

function renderServices() {
  const serviceSelect = $("#serviceSelect");
  serviceSelect.innerHTML = `<option value="">Select service</option>` + state.services.map((service) => (
    `<option value="${escapeHtml(service.name)}">${escapeHtml(service.name)}</option>`
  )).join("");

  $("#serviceGrid").innerHTML = state.services.map((service) => `
    <article>
      <h3>${escapeHtml(service.name)}</h3>
      <p>${escapeHtml(service.description)}</p>
    </article>
  `).join("");
}

function renderPromos() {
  $("#promoGrid").innerHTML = state.promos.map((promo) => `
    <article class="promo-card">
      <strong>${escapeHtml(promo.title)}</strong>
      <p>${escapeHtml(promo.description)}</p>
    </article>
  `).join("");
}

function jumpToDashboard() {
  if (!state.user) {
    openAuth("login");
    return;
  }
  window.location.href = dashboardUrl(state.user.role);
}

async function submitAppointment(event) {
  event.preventDefault();
  if (!state.user) {
    openAuth("login");
    showToast("Please log in or create a patient account to book.", "error");
    return;
  }
  if (state.user.role !== "patient") {
    showToast("Doctor accounts manage appointments from the dashboard.", "error");
    return;
  }
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  try {
    await api("/api/appointments", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    resetAppointmentForm();
    queueToast("Appointment request saved.");
    window.location.href = "patient-dashboard.html";
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    state.user = data.user;
    queueToast(`Welcome back, ${state.user.name}.`);
    window.location.href = dashboardUrl(state.user.role);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitRegister(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  try {
    const data = await api("/api/register", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    state.user = data.user;
    queueToast(`Account created for ${state.user.name}.`);
    window.location.href = dashboardUrl(state.user.role);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function logout() {
  try {
    await api("/api/logout", { method: "POST", body: "{}" });
    state.user = null;
    state.csrfToken = "";
    updateAuthUI();
    showToast("Logged out.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function loadFeedback() {
  const data = await api("/api/feedback");
  state.feedback = data.feedback;
  renderFeedback();
}

function renderFeedback() {
  const wrap = $("#feedbackList");
  wrap.innerHTML = state.feedback.length
    ? state.feedback.slice(0, 6).map((item) => `
      <article class="feedback-item">
        <div class="stars">Rating ${escapeHtml(item.rating)}/5</div>
        <h4>${escapeHtml(item.name)}</h4>
        <p>${escapeHtml(item.message)}</p>
      </article>
    `).join("")
    : `<div class="empty-state">No feedback yet.</div>`;
}

async function submitFeedback(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  try {
    await api("/api/feedback", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    form.reset();
    showToast("Thank you for the feedback.");
    await loadFeedback();
    updateAuthUI();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function bindEvents() {
  $("#appointmentForm").addEventListener("submit", submitAppointment);
  $("#appointmentDate").addEventListener("change", renderTimeSlots);
  $("#loginForm").addEventListener("submit", submitLogin);
  $("#registerForm").addEventListener("submit", submitRegister);
  $("#feedbackForm").addEventListener("submit", submitFeedback);
  $("#loginOpen").addEventListener("click", () => openAuth("login"));
  $("#registerOpen").addEventListener("click", () => openAuth("register"));
  $("#authClose").addEventListener("click", closeAuth);
  $("#authModal").addEventListener("click", (event) => {
    if (event.target.id === "authModal") closeAuth();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("#authModal").classList.contains("hidden")) {
      closeAuth();
    }
  });
  $$("[data-auth-tab]").forEach((button) => {
    button.addEventListener("click", () => switchAuthTab(button.dataset.authTab));
  });
  $("#passwordToggle").addEventListener("click", () => {
    setLoginPasswordVisible($("#loginPassword").type === "password");
  });
  $("#forgotPassword").addEventListener("click", () => {
    showToast("Please contact clinic staff to reset your password.", "success");
  });
  $("#registerRole").addEventListener("change", (event) => {
    $("#staffCodeWrap").classList.toggle("hidden", event.target.value !== "doctor");
  });
  $("#logoutButton").addEventListener("click", logout);
  $("#dashboardJump").addEventListener("click", jumpToDashboard);
  $("#heroBook").addEventListener("click", () => {
    $("#appointmentForm").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("#bookNav").addEventListener("click", () => {
    $("#appointmentForm").scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

async function boot() {
  renderBookingDentists();
  bindEvents();
  consumeQueuedToast();
  if (new URLSearchParams(window.location.search).get("login") === "1") {
    openAuth("login");
  }
  try {
    await Promise.all([loadSession(), loadFeedback(), loadServices(), loadPromos(), loadAvailability()]);
  } catch (error) {
    showToast(error.message, "error");
  }
}

document.addEventListener("DOMContentLoaded", boot);
