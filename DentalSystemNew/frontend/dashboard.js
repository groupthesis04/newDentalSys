const page = document.body.dataset.page;

const state = {
  user: null,
  csrfToken: "",
  appointments: [],
  availability: [],
  records: [],
  patients: [],
  messages: [],
  notifications: [],
  contacts: [],
  feedback: [],
  services: [],
  promos: [],
  clinicDoctor: "",
  selectedPatientId: "",
  selectedService: "Oral Prophylaxis",
  selectedOverviewDate: ""
};

const selectedAvailabilityDates = new Set();
let notificationPollTimer = null;

const dentalServiceCategories = [
  "Oral Prophylaxis",
  "Tooth Extraction",
  "Dental Filling",
  "Root Canal Treatment",
  "Dental Crown",
  "Dental Bridge",
  "Dentures",
  "Orthodontics (Braces)",
  "Teeth Whitening",
  "Dental X-ray",
  "Consultation",
  "Fluoride Treatment",
  "Dental Sealants",
  "Others"
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

function actionIcon(action) {
  const iconIds = { view: "action-icon-eye", edit: "action-icon-pencil", delete: "action-icon-trash" };
  const iconId = iconIds[action];
  return iconId
    ? `<svg class="button-icon" aria-hidden="true" focusable="false"><use href="#${iconId}"></use></svg>`
    : "";
}

function setText(selector, value) {
  const element = $(selector);
  if (element) element.textContent = value;
}

function setValue(selector, value) {
  const element = $(selector);
  if (element) element.value = value ?? "";
}

function formatDate(value) {
  if (!value) return "-";
  const [year, month, day] = value.split("-");
  return `${month}/${day}/${year}`;
}

function localDateIso(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function todayIso() {
  return localDateIso();
}

function currentMonthIso() {
  return todayIso().slice(0, 7);
}

function availabilityMaxDateIso() {
  const maximum = new Date();
  maximum.setDate(maximum.getDate() + 365);
  return localDateIso(maximum);
}

function calculateAge(birthdate) {
  if (!birthdate) return "";
  const born = new Date(`${birthdate}T00:00:00`);
  if (Number.isNaN(born.getTime())) return "";
  const today = new Date();
  let age = today.getFullYear() - born.getFullYear();
  const hasHadBirthday = today.getMonth() > born.getMonth()
    || (today.getMonth() === born.getMonth() && today.getDate() >= born.getDate());
  if (!hasHadBirthday) age -= 1;
  return Math.max(age, 0);
}

function formatMoney(value) {
  const amount = Number(value || 0);
  return `PHP ${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function initialsFromName(name) {
  return String(name || "Patient")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("") || "P";
}

function moneyValue(value) {
  const amount = Number(value || 0);
  return Number.isFinite(amount) ? amount : 0;
}

function treatmentDate(record) {
  return record.treatment_date || String(record.created_at || "").slice(0, 10);
}

function treatmentProcedure(record) {
  return record.procedure || record.treatment || record.diagnosis || "Treatment";
}

function treatmentBalance(record) {
  if (record.balance !== undefined && record.balance !== null) return moneyValue(record.balance);
  return moneyValue(record.amount_charged) - moneyValue(record.amount_paid);
}

function paymentStatus(record) {
  return treatmentBalance(record) <= 0 ? "completed" : "unpaid";
}

function patientRecords(patientId) {
  return state.records.filter((record) => record.patient_id === patientId);
}

function patientTotals(patientId) {
  const records = patientRecords(patientId);
  return records.reduce((totals, record) => {
    totals.charged += moneyValue(record.amount_charged);
    totals.paid += moneyValue(record.amount_paid);
    totals.balance += treatmentBalance(record);
    return totals;
  }, { charged: 0, paid: 0, balance: 0 });
}

function upsertRecord(record) {
  if (!record?.id) return;
  const index = state.records.findIndex((item) => item.id === record.id);
  if (index >= 0) {
    state.records[index] = record;
  } else {
    state.records.unshift(record);
  }
}

function allProcedureOptions() {
  const existing = state.services.map((service) => service.name);
  const procedures = state.records.map(treatmentProcedure);
  return Array.from(new Set([...dentalServiceCategories, ...existing, ...procedures].filter(Boolean)));
}

function procedureOptions(selected = "") {
  return allProcedureOptions().map((procedure) => (
    `<option value="${escapeHtml(procedure)}" ${procedure === selected ? "selected" : ""}>${escapeHtml(procedure)}</option>`
  )).join("");
}

function formatDateTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString();
}

function dashboardUrl(role) {
  return role === "doctor" ? "doctor-dashboard.html" : "patient-dashboard.html";
}

function getInitials(name) {
  const parts = String(name || "User").trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() || "").join("") || "U";
}

function setAvatar(selector, name, image) {
  const element = $(selector);
  if (!element) return;
  element.style.backgroundImage = "";
  element.style.backgroundSize = "";
  element.style.backgroundPosition = "";
  if (image) {
    element.textContent = "";
    element.style.backgroundImage = `url("${image.replaceAll('"', "%22")}")`;
    element.style.backgroundSize = "cover";
    element.style.backgroundPosition = "center";
  } else {
    element.textContent = getInitials(name);
  }
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

function openCrudDialog(selector) {
  const dialog = $(selector);
  if (!dialog || dialog.open) return;
  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "");
  }
}

function closeCrudDialog(selector) {
  const dialog = $(selector);
  if (!dialog?.open) return;
  if (typeof dialog.close === "function") {
    dialog.close();
  } else {
    dialog.removeAttribute("open");
  }
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
  const method = String(options.method || "GET").toUpperCase();
  const headers = {
    "X-Requested-With": "DentalSystem",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(state.csrfToken && method !== "GET" ? { "X-CSRF-Token": state.csrfToken } : {}),
    ...(options.headers || {})
  };
  const response = await fetch(path, {
    ...options,
    method,
    credentials: "same-origin",
    headers
  });
  const body = await response.json().catch(() => ({}));
  if (body.csrf_token) state.csrfToken = body.csrf_token;
  if (!response.ok) {
    throw new Error(body.error || "Something went wrong.");
  }
  return body;
}

function statusLabel(status) {
  const labels = { pending: "Pending", approved: "Accepted", accepted: "Accepted", completed: "Completed", cancelled: "Cancelled" };
  return `<span class="status ${escapeHtml(status)}">${escapeHtml(labels[status] || status)}</span>`;
}

function countStatus(status) {
  return state.appointments.filter((item) => item.status === status).length;
}

function sortAppointmentsNewest(appointments) {
  return [...appointments].sort((left, right) => {
    const leftCreated = String(left.created_at || `${left.date || ""}T${left.time || ""}`);
    const rightCreated = String(right.created_at || `${right.date || ""}T${right.time || ""}`);
    return rightCreated.localeCompare(leftCreated);
  });
}

function nextActiveAppointment() {
  return [...state.appointments]
    .filter((item) => !["cancelled", "completed"].includes(item.status))
    .sort((left, right) => (
      `${left.date || ""}T${left.time || ""}`.localeCompare(`${right.date || ""}T${right.time || ""}`)
    ))[0] || null;
}

function formatNotificationTime(value) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "";
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - timestamp.getTime()) / 1000));
  if (elapsedSeconds < 60) return "Just now";
  if (elapsedSeconds < 3600) return `${Math.floor(elapsedSeconds / 60)}m ago`;
  if (elapsedSeconds < 86400) return `${Math.floor(elapsedSeconds / 3600)}h ago`;
  return timestamp.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

function renderNotifications() {
  const button = $("#notificationButton");
  const badge = $("#notificationBadge");
  const list = $("#notificationList");
  const readAll = $("#notificationReadAll");
  if (!button || !badge || !list || !readAll) return;

  const unreadCount = state.notifications.filter((item) => !item.is_read).length;
  badge.textContent = unreadCount > 99 ? "99+" : String(unreadCount);
  badge.setAttribute(
    "aria-label",
    `${unreadCount} unread notification${unreadCount === 1 ? "" : "s"}`
  );
  badge.classList.toggle("hidden", unreadCount === 0);
  button.setAttribute(
    "aria-label",
    unreadCount
      ? `Notifications, ${unreadCount} unread`
      : "Notifications"
  );
  readAll.disabled = unreadCount === 0;

  list.innerHTML = state.notifications.length
    ? state.notifications.map((item) => `
      <button class="notification-item ${item.is_read ? "" : "unread"}" data-notification-id="${escapeHtml(item.id)}" type="button">
        <span class="notification-item-indicator" aria-hidden="true"></span>
        <span class="notification-item-content">
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.message)}</span>
          <time datetime="${escapeHtml(item.created_at)}">${escapeHtml(formatNotificationTime(item.created_at))}</time>
        </span>
      </button>
    `).join("")
    : `<p class="notification-empty">No notifications yet.</p>`;
}

function setNotificationPanelOpen(open) {
  const button = $("#notificationButton");
  const panel = $("#notificationPanel");
  if (!button || !panel) return;
  panel.classList.toggle("hidden", !open);
  button.setAttribute("aria-expanded", String(open));
}

async function refreshNotifications(showErrors = false) {
  try {
    const data = await api("/api/notifications");
    state.notifications = data.notifications || [];
    renderNotifications();
  } catch (error) {
    if (showErrors) showToast(error.message, "error");
  }
}

function revealNotificationTarget(containerSelector, entityId) {
  const container = $(containerSelector);
  const target = container
    ? [...container.querySelectorAll("[data-entity-id]")]
      .find((element) => element.dataset.entityId === String(entityId || ""))
    : null;
  if (!target) {
    showToast("This transaction is no longer available in the current records.", "error");
    return;
  }

  $$(".notification-target-glow").forEach((element) => {
    element.classList.remove("notification-target-glow");
  });
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
      target.classList.add("notification-target-glow");
      clearTimeout(revealNotificationTarget.timer);
      revealNotificationTarget.timer = window.setTimeout(() => {
        target.classList.remove("notification-target-glow");
      }, 3200);
    });
  });
}

function openNotificationTarget(notification) {
  if (!notification) return;
  if (notification.entity_type === "appointment") {
    const panelId = page === "doctor" ? "doctorSchedule" : "patientSchedule";
    showPanel(panelId);
    revealNotificationTarget(`#${panelId}`, notification.entity_id);
  } else if (notification.entity_type === "treatment") {
    if (page === "doctor") {
      showPanel("doctorPatients");
      const record = state.records.find((item) => item.id === notification.entity_id);
      if (!record) {
        showToast("This treatment is no longer available in the current records.", "error");
        return;
      }
      openPatientProfile(record.patient_id);
      revealNotificationTarget("#patientProfileDialog", notification.entity_id);
    } else {
      showPanel("patientOverview");
      revealNotificationTarget("#patientOverview", notification.entity_id);
    }
  }
}

async function markNotificationsRead(notificationId = "") {
  try {
    await api("/api/notifications", {
      method: "PATCH",
      body: JSON.stringify(notificationId ? { id: notificationId } : { mark_all: true })
    });
    state.notifications.forEach((item) => {
      if (!notificationId || item.id === notificationId) item.is_read = true;
    });
    renderNotifications();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function startNotificationPolling() {
  clearInterval(notificationPollTimer);
  notificationPollTimer = window.setInterval(() => {
    if (!document.hidden) refreshNotifications(false);
  }, 30000);
}

function contactName(id) {
  const contact = state.contacts.find((item) => item.id === id);
  return contact?.name || "Contact";
}

function renderMessages(prefix) {
  const select = $(`#${prefix}MessageContact`);
  const list = $(`#${prefix}MessagesList`);
  if (!select || !list) return;

  const previous = select.value;
  select.innerHTML = state.contacts.length
    ? state.contacts.map((contact) => `<option value="${escapeHtml(contact.id)}">${escapeHtml(contact.name)}</option>`).join("")
    : `<option value="">No contacts available</option>`;
  if (state.contacts.some((contact) => contact.id === previous)) {
    select.value = previous;
  }

  const selectedId = select.value;
  const thread = selectedId
    ? state.messages.filter((message) => (
        message.sender_id === selectedId || message.recipient_id === selectedId
      ))
    : [];

  list.innerHTML = thread.length
    ? thread.map((message) => {
        const mine = message.sender_id === state.user.id;
        return `
          <article class="message-item ${mine ? "mine" : ""}">
            <strong>${mine ? "You" : escapeHtml(message.sender_name || contactName(message.sender_id))}</strong>
            <p>${escapeHtml(message.body)}</p>
            <span>${formatDateTime(message.created_at)}</span>
          </article>
        `;
      }).join("")
    : `<div class="empty-state">${state.contacts.length ? "No messages in this conversation yet." : "No message contacts yet."}</div>`;
}

function showPanel(targetId) {
  $$(".workspace-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== targetId);
  });
  $$("[data-panel-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.panelTarget === targetId);
  });
  window.scrollTo({ top: 0, behavior: "auto" });
}

async function requireDashboardRole() {
  const requiredRole = page === "doctor" ? "doctor" : "patient";
  const data = await api("/api/session");
  state.user = data.user;
  state.csrfToken = data.csrf_token || "";
  if (!state.user) {
    queueToast("Please log in to continue.", "error");
    window.location.href = "index.html?login=1";
    return false;
  }
  if (state.user.role !== requiredRole) {
    queueToast("Opening your dashboard.");
    window.location.href = dashboardUrl(state.user.role);
    return false;
  }
  return true;
}

async function logout() {
  try {
    await api("/api/logout", { method: "POST", body: "{}" });
    queueToast("Logged out.");
    window.location.href = "index.html#home";
  } catch (error) {
    showToast(error.message, "error");
  }
}

function updateUserProfile(prefix, roleLabel) {
  setAvatar(`#${prefix}SidebarInitials`, state.user.name, state.user.profile_image);
  setAvatar(`#${prefix}ProfileInitials`, state.user.name, state.user.profile_image);
  setText(`#${prefix}SidebarName`, state.user.name);
  setText(`#${prefix}Name`, state.user.name);
  setText(`#${prefix}ProfileName`, state.user.name);
  setText(`#${prefix}ProfileEmail`, state.user.email);
  setText(`#${prefix}ProfileRole`, roleLabel);
  setText(`#${prefix}ProfileStatus`, "Active");
  setText(`#${prefix}ProfilePhone`, state.user.phone || "Not provided");
  setText(`#${prefix}Role`, roleLabel);
  setText(`#${prefix}Status`, "Active");
  setText(`#${prefix}Phone`, state.user.phone || "Not provided");
  setText(`#${prefix}DetailName`, state.user.name);
  setText(`#${prefix}DetailEmail`, state.user.email);
  setText(`#${prefix}DetailPhone`, state.user.phone || "Not provided");
  setText(`#${prefix}DetailCreated`, formatDateTime(state.user.created_at));
  setValue(`#${prefix}EditName`, state.user.name);
  setValue(`#${prefix}EditEmail`, state.user.email);
  setValue(`#${prefix}EditPhone`, state.user.phone || "");
  setValue(`#${prefix}EditProfileImage`, state.user.profile_image || "");
}

async function loadPatientData() {
  const [appointments, records, messageData, services, availability, notifications] = await Promise.all([
    api("/api/appointments"),
    api("/api/records"),
    api("/api/messages"),
    api("/api/services"),
    api("/api/availability"),
    api("/api/notifications")
  ]);
  state.appointments = sortAppointmentsNewest(appointments.appointments || []);
  state.records = records.records;
  state.messages = messageData.messages;
  state.contacts = messageData.contacts;
  state.services = services.services;
  state.availability = availability.availability;
  state.clinicDoctor = availability.clinic_doctor || "";
  state.notifications = notifications.notifications || [];
  renderPatientDashboard();
}

function renderPatientAppointmentServices() {
  const select = $("#patientAppointmentService");
  if (!select) return;
  const previous = select.value;
  const names = state.services.length
    ? state.services.map((service) => service.name).filter(Boolean)
    : dentalServiceCategories;
  select.innerHTML = `<option value="">Select service</option>${names.map((name) => (
    `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`
  )).join("")}`;
  if (names.includes(previous)) select.value = previous;
}

function renderPatientAppointmentDoctors() {
  const input = $("#patientAppointmentDoctor");
  if (!input) return;
  const scheduledDoctor = state.availability.find((slot) => slot.doctor)?.doctor || "";
  input.value = state.clinicDoctor || scheduledDoctor;
  renderPatientAppointmentDates();
}

function renderPatientAppointmentDates() {
  const select = $("#patientAppointmentDate");
  if (!select) return;
  const previous = select.value;
  const doctor = $("#patientAppointmentDoctor")?.value || "";
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
  renderPatientAppointmentTimeSlots();
}

function renderPatientAppointmentTimeSlots() {
  const wrap = $("#patientAppointmentTimeSlots");
  if (!wrap) return;
  const doctor = $("#patientAppointmentDoctor")?.value || "";
  const date = $("#patientAppointmentDate")?.value || "";
  const slots = state.availability
    .filter((slot) => slot.doctor === doctor && slot.date === date && !slot.booked)
    .sort((left, right) => left.time.localeCompare(right.time));
  wrap.innerHTML = "";
  setValue("#patientAppointmentTime", "");
  setText("#patientAppointmentTimeLabel", "Select slot");
  if (!slots.length) {
    wrap.innerHTML = `<p class="availability-empty">${doctor && date
      ? "No open times remain for this date."
      : "The clinic has not opened an appointment slot yet."}</p>`;
    $("#patientAppointmentSubmit").disabled = true;
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
      setValue("#patientAppointmentTime", slot.time);
      setText("#patientAppointmentTimeLabel", slot.time);
    });
    wrap.appendChild(button);
  });
  $("#patientAppointmentSubmit").disabled = false;
}

function resetPatientAppointmentForm() {
  const form = $("#patientAppointmentForm");
  if (!form) return;
  form.reset();
  renderPatientAppointmentServices();
  renderPatientAppointmentDoctors();
}

function openPatientAppointmentDialog() {
  resetPatientAppointmentForm();
  openCrudDialog("#patientAppointmentDialog");
}

async function submitPatientAppointment(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  if (!payload.time) {
    showToast("Select an appointment time.", "error");
    $("#patientAppointmentTimeSlots .time-slot")?.focus();
    return;
  }
  try {
    await api("/api/appointments", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    closeCrudDialog("#patientAppointmentDialog");
    showToast("Appointment request saved.");
    await loadPatientData();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderPatientAppointmentCards() {
  if (!state.appointments.length) {
    return `<tr><td colspan="5" class="table-empty">No appointments yet.</td></tr>`;
  }
  return state.appointments.map((item) => `
    <tr data-entity-type="appointment" data-entity-id="${escapeHtml(item.id)}">
      <td><strong>${escapeHtml(item.service)}</strong>${item.notes ? `<div class="meta">${escapeHtml(item.notes)}</div>` : ""}</td>
      <td>${escapeHtml(item.doctor)}</td>
      <td>${formatDate(item.date)}<div class="meta">${escapeHtml(item.time)}</div></td>
      <td>${statusLabel(item.status)}</td>
      <td>${item.status !== "cancelled" && item.status !== "completed"
        ? `<button class="danger-button compact-button cancel-appointment" data-id="${escapeHtml(item.id)}" type="button">Cancel</button>`
        : `<span class="meta">No action</span>`}</td>
    </tr>
  `).join("");
}

function renderPatientRecords() {
  const recordsWrap = $("#patientRecords");
  recordsWrap.innerHTML = state.records.length
    ? state.records.map((record) => `
      <tr data-entity-type="treatment" data-entity-id="${escapeHtml(record.id)}">
        <td>${formatDate(treatmentDate(record))}</td>
        <td><strong>${escapeHtml(treatmentProcedure(record))}</strong>${record.remarks || record.notes ? `<div class="meta">${escapeHtml(record.remarks || record.notes)}</div>` : ""}</td>
        <td>${escapeHtml(record.tooth_numbers || "-")}</td>
        <td>${escapeHtml(record.doctor_name || "Dentist")}</td>
        <td>${formatMoney(treatmentBalance(record))}</td>
      </tr>
    `).join("")
    : `<tr><td colspan="5" class="table-empty">No dental records have been added yet.</td></tr>`;
}

function renderPatientDashboard() {
  updateUserProfile("patient", "Patient");
  renderPatientAppointmentServices();
  renderPatientAppointmentDoctors();
  const next = nextActiveAppointment();
  setText("#nextVisitSummary", next ? `${formatDate(next.date)} at ${next.time}` : "No appointment yet");
  setText("#appointmentCount", state.appointments.length);
  setText("#recordCount", state.records.length);
  renderNotifications();

  const appointmentCards = renderPatientAppointmentCards();
  $("#patientAppointments").innerHTML = appointmentCards;
  $("#patientScheduleList").innerHTML = appointmentCards;
  renderPatientRecords();
  renderMessages("patient");

  $$(".cancel-appointment").forEach((button) => {
    button.addEventListener("click", () => updateAppointmentStatus(button.dataset.id, "cancelled"));
  });
}

async function submitPatientProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  try {
    const data = await api("/api/profile", {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
    state.user = data.user;
    showToast("Profile updated.");
    renderPatientDashboard();
    showPanel("patientProfile");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitDoctorProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  try {
    const data = await api("/api/profile", {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
    state.user = data.user;
    showToast("Profile updated.");
    renderDoctorDashboard();
    showPanel("doctorProfile");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function loadDoctorData() {
  const [appointments, records, patients, feedback, services, promos, messageData, availability, notifications] = await Promise.all([
    api("/api/appointments"),
    api("/api/records"),
    api("/api/patients"),
    api("/api/feedback"),
    api("/api/services"),
    api("/api/promos"),
    api("/api/messages"),
    api("/api/availability"),
    api("/api/notifications")
  ]);
  state.appointments = sortAppointmentsNewest(appointments.appointments || []);
  state.records = records.records;
  state.patients = patients.patients;
  state.feedback = feedback.feedback;
  state.services = services.services;
  state.promos = promos.promos;
  state.messages = messageData.messages;
  state.contacts = messageData.contacts;
  state.availability = availability.availability;
  state.clinicDoctor = availability.clinic_doctor || state.user.name;
  state.notifications = notifications.notifications || [];
  renderDoctorDashboard();
}

function doctorAppointmentRows() {
  return state.appointments.length
    ? state.appointments.map((item) => `
      <tr data-entity-type="appointment" data-entity-id="${escapeHtml(item.id)}">
        <td>
          <strong>${escapeHtml(item.patient_name)}</strong>
          <div class="meta">${escapeHtml(item.patient_email)}</div>
        </td>
        <td>${escapeHtml(item.service)}</td>
        <td>${formatDate(item.date)}</td>
        <td>${escapeHtml(item.time)}</td>
        <td>
          <select class="status-select status-${escapeHtml(item.status)}" data-id="${escapeHtml(item.id)}">
            ${[
              ["pending", "Pending"],
              ["approved", "Accepted"],
              ["completed", "Completed"],
              ["cancelled", "Cancelled"]
            ].map(([status, label]) => `
              <option value="${status}" ${status === item.status ? "selected" : ""}>${label}</option>
            `).join("")}
          </select>
        </td>
      </tr>
    `).join("")
    : `<tr><td colspan="5">No appointments yet.</td></tr>`;
}

function overviewDates() {
  const basis = new Date(`${state.selectedOverviewDate || todayIso()}T00:00:00`);
  const start = new Date(basis);
  start.setDate(basis.getDate() - basis.getDay());
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return {
      iso: localDateIso(date),
      day: date.toLocaleDateString(undefined, { weekday: "short" }),
      date: date.getDate()
    };
  });
}

function renderDoctorDayStrip() {
  const strip = $("#doctorDayStrip");
  if (!strip) return;
  const dates = overviewDates();
  if (!dates.some((item) => item.iso === state.selectedOverviewDate)) {
    state.selectedOverviewDate = dates.find((item) => item.iso === todayIso())?.iso || dates[0].iso;
  }
  const rangeStart = $("#dashboardRangeStart");
  const rangeEnd = $("#dashboardRangeEnd");
  if (rangeStart && !rangeStart.value) rangeStart.value = dates[0].iso;
  if (rangeEnd && !rangeEnd.value) {
    const end = new Date(`${dates[0].iso}T00:00:00`);
    end.setDate(end.getDate() + 29);
    rangeEnd.value = localDateIso(end);
  }
  strip.innerHTML = dates.map((item) => `
    <button class="dashboard-day-button ${item.iso === state.selectedOverviewDate ? "active" : ""}" data-overview-date="${item.iso}" type="button" aria-pressed="${item.iso === state.selectedOverviewDate}">
      <span>${escapeHtml(item.day)}</span>
      <strong>${item.date}</strong>
    </button>
  `).join("");
}

function renderDoctorDailySchedule() {
  const list = $("#doctorDailySchedule");
  if (!list) return;
  const appointments = state.appointments
    .filter((item) => item.date === state.selectedOverviewDate && item.status !== "cancelled")
    .sort((left, right) => String(left.time || "").localeCompare(String(right.time || "")));
  setText("#doctorTodayCount", `${appointments.length} appointment${appointments.length === 1 ? "" : "s"}`);
  list.innerHTML = appointments.length
    ? appointments.map((item) => {
      const patient = state.patients.find((candidate) => candidate.id === item.patient_id);
      const avatar = patient?.profile_image
        ? `<img class="reference-appointment-avatar" src="${escapeHtml(patient.profile_image)}" alt="">`
        : `<span class="reference-appointment-avatar" aria-hidden="true">${escapeHtml(initialsFromName(item.patient_name))}</span>`;
      return `
        <article class="reference-appointment-card" data-entity-type="appointment" data-entity-id="${escapeHtml(item.id)}">
          ${avatar}
          <strong>${escapeHtml(item.patient_name)}</strong>
          <span>${escapeHtml(item.service)}</span>
          <time datetime="${escapeHtml(`${item.date}T${item.time}`)}">${escapeHtml(item.time)}</time>
          ${statusLabel(item.status)}
        </article>
      `;
    }).join("")
    : `<p class="dashboard-empty">No appointments scheduled for this date.</p>`;
}

function renderDoctorPendingAppointments() {
  const list = $("#doctorPendingAppointments");
  if (!list) return;
  const pending = state.appointments.filter((item) => item.status === "pending");
  setText("#doctorPendingBadge", `${pending.length} pending`);
  list.innerHTML = pending.length
    ? pending.slice(0, 5).map((item) => `
      <article class="pending-appointment-card" data-entity-type="appointment" data-entity-id="${escapeHtml(item.id)}">
        <div>
          <h3>${escapeHtml(item.patient_name)}</h3>
          <p>${escapeHtml(item.service)} &middot; ${formatDate(item.date)} at ${escapeHtml(item.time)}</p>
        </div>
        <div class="appointment-decision-actions">
          <button class="appointment-accept appointment-decision" data-id="${escapeHtml(item.id)}" data-status="approved" type="button">Accept</button>
          <button class="appointment-decline appointment-decision" data-id="${escapeHtml(item.id)}" data-status="cancelled" type="button">Decline</button>
        </div>
      </article>
    `).join("")
    : `<p class="dashboard-empty">No appointment requests are waiting.</p>`;
}

function renderDoctorServiceSnapshot() {
  const list = $("#doctorServiceSnapshot");
  if (!list) return;
  const counts = new Map();
  state.records.forEach((record) => {
    const procedure = treatmentProcedure(record);
    counts.set(procedure, (counts.get(procedure) || 0) + 1);
  });
  const availableNames = state.services.length
    ? state.services.map((service) => service.name)
    : dentalServiceCategories;
  const services = availableNames.slice(0, 7).map((name) => [name, counts.get(name) || 0]);
  list.innerHTML = services.length
    ? services.map(([name, count]) => `
      <button class="treatment-tile" data-panel-target="doctorPatients" data-service-category="${escapeHtml(name)}" type="button">
        <span class="treatment-tile-icon" aria-hidden="true">${escapeHtml(initialsFromName(name))}</span>
        <strong>${escapeHtml(name)}</strong>
        <small>${count} completed treatment${count === 1 ? "" : "s"}</small>
      </button>
    `).join("")
    : `<p class="dashboard-empty">No dental services have been added.</p>`;
}

function renderDoctorIncomeChart() {
  const chart = $("#doctorIncomeChart");
  if (!chart) return;
  const now = new Date();
  const months = Array.from({ length: 12 }, (_, offset) => {
    const date = new Date(now.getFullYear(), now.getMonth() - (11 - offset), 1);
    return {
      key: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`,
      label: date.toLocaleDateString(undefined, { month: "short" }),
      value: 0
    };
  });
  const byMonth = new Map(months.map((month) => [month.key, month]));
  state.records.forEach((record) => {
    const month = byMonth.get(treatmentDate(record).slice(0, 7));
    if (month) month.value += moneyValue(record.amount_paid);
  });
  const maximum = Math.max(1, ...months.map((month) => month.value));
  const total = months.reduce((sum, month) => sum + month.value, 0);
  setText("#doctorIncomeTotal", formatMoney(total));
  chart.innerHTML = months.map((month) => `
    <div class="income-chart-column">
      <div class="income-chart-value" title="${escapeHtml(`${month.label}: ${formatMoney(month.value)}`)}">
        <span style="height:${Math.max(month.value ? 8 : 2, (month.value / maximum) * 100)}%"></span>
      </div>
      <small>${escapeHtml(month.label)}</small>
    </div>
  `).join("");
}

function renderDoctorActivityFeed() {
  const feed = $("#doctorActivityFeed");
  if (!feed) return;
  const activities = state.notifications.slice(0, 5).map((item) => ({
    title: item.title,
    message: item.message,
    time: formatNotificationTime(item.created_at)
  }));
  if (!activities.length) {
    state.records.slice(0, 5).forEach((record) => activities.push({
      title: `${record.patient_name} treatment updated`,
      message: treatmentProcedure(record),
      time: formatDate(treatmentDate(record))
    }));
  }
  feed.innerHTML = activities.length
    ? activities.map((item) => `
      <article class="clinic-activity-item">
        <span class="activity-indicator" aria-hidden="true"></span>
        <div><time>${escapeHtml(item.time)}</time><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.message)}</p></div>
      </article>
    `).join("")
    : `<p class="dashboard-empty">No clinic activity has been recorded.</p>`;
}

function analyticsRows(items) {
  const maximum = Math.max(1, ...items.map((item) => item.value));
  return items.map((item) => `
    <div class="analytics-bar-row ${escapeHtml(item.status || "")}">
      <div><span>${escapeHtml(item.label)}</span><strong>${item.value}</strong></div>
      <span class="analytics-track" aria-hidden="true"><span style="width:${Math.round((item.value / maximum) * 100)}%"></span></span>
    </div>
  `).join("");
}

function renderDoctorAnalytics() {
  const patientChart = $("#doctorPatientAnalytics");
  const appointmentChart = $("#doctorAppointmentAnalytics");
  if (patientChart) {
    const treated = new Set(state.records.map((record) => record.patient_id)).size;
    const withBalance = new Set(state.records.filter((record) => treatmentBalance(record) > 0).map((record) => record.patient_id)).size;
    patientChart.innerHTML = analyticsRows([
      { label: "Registered patients", value: state.patients.length },
      { label: "With treatment history", value: treated },
      { label: "With outstanding balance", value: withBalance }
    ]);
  }
  if (appointmentChart) {
    appointmentChart.innerHTML = analyticsRows([
      { label: "Pending", value: countStatus("pending"), status: "pending" },
      { label: "Accepted", value: countStatus("approved"), status: "approved" },
      { label: "Completed", value: countStatus("completed"), status: "completed" },
      { label: "Cancelled", value: countStatus("cancelled"), status: "cancelled" }
    ]);
  }
}

function renderDoctorOverviewWidgets() {
  const today = todayIso();
  const pendingCount = countStatus("pending");
  const totals = state.records.reduce((summary, record) => {
    summary.charged += moneyValue(record.amount_charged);
    summary.paid += moneyValue(record.amount_paid);
    summary.balance += treatmentBalance(record);
    return summary;
  }, { charged: 0, paid: 0, balance: 0 });
  const collectionRate = totals.charged > 0
    ? Math.min(100, Math.max(0, (totals.paid / totals.charged) * 100))
    : 0;

  setText("#doctorDashboardDate", new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric"
  }));
  setText("#doctorTodayCount", state.appointments.filter((item) => item.date === today && item.status !== "cancelled").length);
  setText("#doctorPendingOverview", `${pendingCount} pending`);
  setText("#doctorOutstandingBalance", formatMoney(totals.balance));
  setText("#doctorTotalCharged", formatMoney(totals.charged));
  setText("#doctorTotalPaid", formatMoney(totals.paid));
  setText("#doctorTotalOutstanding", formatMoney(totals.balance));
  setText("#doctorBalancePaid", formatMoney(totals.paid));
  setText("#doctorBalanceOutstanding", formatMoney(totals.balance));
  setText("#doctorCollectionRateLabel", `${Math.round(collectionRate)}% collected`);
  const meter = $("#doctorCollectionMeter");
  if (meter) meter.style.width = `${collectionRate.toFixed(1)}%`;

  renderDoctorDayStrip();
  renderDoctorDailySchedule();
  renderDoctorPendingAppointments();
  renderDoctorServiceSnapshot();
  renderDoctorIncomeChart();
  renderDoctorActivityFeed();
  renderDoctorAnalytics();
}

function availabilityRowsHtml(slots, emptyMessage) {
  return slots.length
    ? slots.map((slot) => {
      const pendingCount = Number(slot.pending_count || 0);
      const locked = Boolean(slot.booked || pendingCount);
      const status = slot.booked
        ? '<span class="status approved">Accepted</span>'
        : pendingCount
          ? `<span class="status pending">${pendingCount} Pending</span>`
          : '<span class="status completed">Open</span>';
      const lockedTitle = pendingCount
        ? "Slots with appointment requests cannot be changed"
        : "Accepted slots cannot be changed";
      return `
        <tr>
          <td><strong>${escapeHtml(slot.doctor)}</strong></td>
          <td>${formatDate(slot.date)}</td>
          <td>${escapeHtml(slot.time)}</td>
          <td>${status}</td>
          <td>
            <div class="table-actions">
              <button class="secondary-button compact-button icon-action-button edit-availability" data-id="${escapeHtml(slot.id)}" type="button" aria-label="Edit availability" title="${escapeHtml(locked ? lockedTitle : "Edit availability")}" ${locked ? "disabled" : ""}>${actionIcon("edit")}</button>
              <button class="danger-button compact-button icon-action-button delete-availability" data-id="${escapeHtml(slot.id)}" type="button" aria-label="Delete availability" title="${escapeHtml(locked ? lockedTitle : "Delete availability")}" ${locked ? "disabled" : ""}>${actionIcon("delete")}</button>
            </div>
          </td>
        </tr>
      `;
    }).join("")
    : `<tr><td colspan="5" class="table-empty">${escapeHtml(emptyMessage)}</td></tr>`;
}

function renderAvailabilityRows() {
  const rows = $("#availabilityRows");
  if (!rows) return;
  rows.innerHTML = availabilityRowsHtml(
    state.availability.slice(0, 5),
    "No clinic availability has been added."
  );
  const modalRows = $("#availabilityModalRows");
  if (modalRows) {
    modalRows.innerHTML = availabilityRowsHtml(
      state.availability,
      "No clinic availability has been added."
    );
  }
  const moreButton = $("#openAvailabilityListDialog");
  if (moreButton) moreButton.classList.toggle("hidden", state.availability.length <= 5);
  const moreFooter = $("#availabilityListFooter");
  if (moreFooter) moreFooter.classList.toggle("hidden", state.availability.length <= 5);
  renderAvailabilityCalendar();
}

function syncAvailabilitySelection() {
  const dates = Array.from(selectedAvailabilityDates).sort();
  setValue("#availabilitySelectedDates", dates.join(","));
  setText("#availabilitySelectedCount", `${dates.length} ${dates.length === 1 ? "date" : "dates"} selected`);
}

function renderAvailabilityCalendar() {
  const calendar = $("#availabilityCalendar");
  const monthInput = $("#availabilityMonth");
  if (!calendar || !monthInput) return;
  const minimumMonth = currentMonthIso();
  const maximumDate = availabilityMaxDateIso();
  const maximumMonth = maximumDate.slice(0, 7);
  monthInput.min = minimumMonth;
  monthInput.max = maximumMonth;
  if (!/^\d{4}-\d{2}$/.test(monthInput.value)
      || monthInput.value < minimumMonth
      || monthInput.value > maximumMonth) {
    monthInput.value = minimumMonth;
  }

  const monthValue = monthInput.value;
  Array.from(selectedAvailabilityDates).forEach((value) => {
    if (!value.startsWith(`${monthValue}-`)) selectedAvailabilityDates.delete(value);
  });
  const [year, month] = monthValue.split("-").map(Number);
  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const dayCount = new Date(year, month, 0).getDate();
  const today = todayIso();
  const cells = Array.from({ length: firstWeekday }, () => '<span class="availability-calendar-spacer" aria-hidden="true"></span>');
  for (let day = 1; day <= dayCount; day += 1) {
    const dateValue = `${monthValue}-${String(day).padStart(2, "0")}`;
    const disabled = dateValue < today || dateValue > maximumDate;
    const selected = selectedAvailabilityDates.has(dateValue);
    const hasSlots = state.availability.some((slot) => slot.date === dateValue);
    const dateLabel = new Date(year, month - 1, day).toLocaleDateString(undefined, {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric"
    });
    cells.push(`
      <button class="availability-day${selected ? " selected" : ""}${hasSlots ? " has-slots" : ""}"
        type="button" data-availability-date="${dateValue}" aria-label="${escapeHtml(dateLabel)}"
        aria-pressed="${selected}" ${disabled ? "disabled" : ""}>
        <span>${day}</span>
      </button>
    `);
  }
  calendar.innerHTML = cells.join("");
  syncAvailabilitySelection();
}

function clearAvailabilityDates() {
  selectedAvailabilityDates.clear();
  renderAvailabilityCalendar();
}

function resetAvailabilityForm() {
  const form = $("#availabilityForm");
  if (!form) return;
  form.reset();
  setValue("#availabilityDoctor", state.user?.name || state.clinicDoctor);
  setValue("#availabilityMonth", currentMonthIso());
  clearAvailabilityDates();
}

function editAvailability(id) {
  const slot = state.availability.find((item) => item.id === id);
  if (!slot || slot.booked || Number(slot.pending_count || 0)) return;
  closeCrudDialog("#availabilityListDialog");
  setValue("#availabilityEditorId", slot.id);
  setValue("#availabilityEditorDoctor", slot.doctor);
  setValue("#availabilityEditorDate", slot.date);
  setValue("#availabilityEditorTime", slot.time);
  openCrudDialog("#availabilityEditorDialog");
  $("#availabilityEditorDoctor").focus();
}

async function deleteAvailability(id) {
  const slot = state.availability.find((item) => item.id === id);
  if (!slot || slot.booked || Number(slot.pending_count || 0)) return;
  if (!confirmDelete(`${slot.doctor} availability on ${formatDate(slot.date)} at ${slot.time}`)) return;
  try {
    await api("/api/availability", {
      method: "DELETE",
      body: JSON.stringify({ id })
    });
    showToast("Availability deleted.");
    await loadDoctorData();
    showPanel("doctorSchedule");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderRecordAppointmentOptions() {
  const selectedPatient = $("#recordPatient").value;
  const patientAppointments = state.appointments.filter((item) => item.patient_id === selectedPatient);
  $("#recordAppointment").innerHTML = `<option value="">None</option>` + patientAppointments.map((item) => `
    <option value="${escapeHtml(item.id)}">${formatDate(item.date)} ${escapeHtml(item.time)} - ${escapeHtml(item.service)}</option>
  `).join("");
}

function renderDoctorRecords() {
  const recordsList = $("#doctorRecords");
  if (!recordsList) return;
  recordsList.innerHTML = state.records.length
    ? state.records.slice(0, 5).map((record) => `
      <article class="record-item">
        <header>
          <div>
            <h4>${escapeHtml(record.patient_name)}</h4>
            <p class="meta">${formatDate(treatmentDate(record))} &middot; ${escapeHtml(record.doctor_name)}</p>
          </div>
        </header>
        <p><strong>Procedure:</strong> ${escapeHtml(treatmentProcedure(record))}</p>
        <p><strong>Tooth No./s:</strong> ${escapeHtml(record.tooth_numbers || "-")}</p>
        <p class="meta">Charged ${formatMoney(record.amount_charged)} &middot; Paid ${formatMoney(record.amount_paid)} &middot; Balance ${formatMoney(treatmentBalance(record))}</p>
        ${record.remarks || record.notes ? `<p class="meta">${escapeHtml(record.remarks || record.notes)}</p>` : ""}
      </article>
    `).join("")
    : `<div class="empty-state">No records have been saved yet.</div>`;
}

function renderDoctorReviews() {
  const reviewCards = $("#doctorReviewCards");
  if (reviewCards) {
    reviewCards.innerHTML = state.feedback.length
      ? state.feedback.slice(0, 4).map((item) => `
        <article class="feedback-item">
          <div class="managed-item">
            <div>
              <div class="stars">Rating ${escapeHtml(item.rating)}/5</div>
              <h4>${escapeHtml(item.name)}</h4>
              <p>${escapeHtml(item.message)}</p>
            </div>
            <button class="danger-button compact-button icon-action-button delete-feedback" data-id="${escapeHtml(item.id)}" data-name="${escapeHtml(item.name)}" type="button" aria-label="Delete feedback from ${escapeHtml(item.name)}" title="Delete feedback">${actionIcon("delete")}</button>
          </div>
        </article>
      `).join("")
      : `<div class="empty-state">No feedback yet.</div>`;
  }

  const feedbackSelect = $("#feedbackSelect");
  feedbackSelect.innerHTML = state.feedback.length
    ? state.feedback.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)} - ${escapeHtml(item.rating)}/5</option>`).join("")
    : `<option value="">No feedback yet</option>`;
  populateFeedbackForm();
}

function populateFeedbackForm() {
  const selected = $("#feedbackSelect").value;
  const item = state.feedback.find((feedback) => feedback.id === selected);
  $("#feedbackRating").value = item ? String(item.rating) : "5";
  $("#feedbackMessage").value = item ? item.message : "";
}

function selectedPatient() {
  const selected = state.patients.find((patient) => patient.id === state.selectedPatientId);
  if (selected) return selected;
  const query = ($("#patientSearch")?.value || "").trim();
  return query ? null : state.patients[0] || null;
}

function resetPatientForm() {
  const form = $("#patientForm");
  if (!form) return;
  form.reset();
  $("#patientEditId").value = "";
  $("#patientAge").value = "";
  setText("#patientFormTitle", "Add Patient");
  $("#patientSubmitButton").textContent = "Save Patient Record";
}

function editPatientForm(patientId) {
  const patient = state.patients.find((item) => item.id === patientId);
  if (!patient) return;
  if (patient.source !== "record") {
    showToast("Patient login accounts manage their own profile. You can still add treatments to their profile.", "error");
    return;
  }
  const form = $("#patientForm");
  $("#patientEditId").value = patient.id;
  form.elements.last_name.value = patient.last_name || "";
  form.elements.first_name.value = patient.first_name || "";
  form.elements.middle_name.value = patient.middle_name || "";
  form.elements.birthdate.value = patient.birthdate || "";
  form.elements.age.value = patient.age || calculateAge(patient.birthdate);
  form.elements.address.value = patient.address || "";
  form.elements.nationality.value = patient.nationality || "";
  form.elements.occupation.value = patient.occupation || "";
  form.elements.phone_number.value = patient.phone_number || "";
  form.elements.mobile_number.value = patient.mobile_number || patient.phone || "";
  form.elements.email.value = patient.email || "";
  form.elements.notes.value = patient.notes || "";
  setText("#patientFormTitle", "Edit Patient");
  $("#patientSubmitButton").textContent = "Update Patient Record";
  showPanel("doctorPatients");
  closeCrudDialog("#patientListDialog");
  openCrudDialog("#patientEditorDialog");
}

function updatePatientAge() {
  const birthdate = $("#patientBirthdate")?.value;
  setValue("#patientAge", calculateAge(birthdate));
}

function updateTreatmentBalance(prefix = "") {
  const chargedSelector = prefix ? `#${prefix}AmountCharged` : "#amountCharged";
  const paidSelector = prefix ? `#${prefix}AmountPaid` : "#amountPaid";
  const balanceSelector = prefix ? `#${prefix}RemainingBalance` : "#remainingBalance";
  const charged = moneyValue($(chargedSelector)?.value);
  const paid = moneyValue($(paidSelector)?.value);
  setValue(balanceSelector, formatMoney(charged - paid));
}

function resetTreatmentForm() {
  const form = $("#treatmentForm");
  if (!form) return;
  const currentProcedure = form.elements.procedure?.value || "";
  form.reset();
  $("#treatmentEditId").value = "";
  $("#treatmentPatientId").value = state.selectedPatientId || "";
  form.elements.treatment_date.value = todayIso();
  if (currentProcedure) form.elements.procedure.value = currentProcedure;
  $("#remainingBalance").value = formatMoney(0);
  setText("#treatmentFormTitle", "Add Treatment");
  $("#treatmentSubmitButton").textContent = "Save Treatment";
}

function editTreatmentForm(recordId) {
  const record = state.records.find((item) => item.id === recordId);
  if (!record) return;
  state.selectedPatientId = record.patient_id;
  renderPatientProfile();
  const form = $("#treatmentForm");
  $("#treatmentEditId").value = record.id;
  $("#treatmentPatientId").value = record.patient_id;
  form.elements.treatment_date.value = treatmentDate(record);
  form.elements.tooth_numbers.value = record.tooth_numbers || "";
  form.elements.procedure.value = treatmentProcedure(record);
  form.elements.amount_charged.value = moneyValue(record.amount_charged).toFixed(2);
  form.elements.amount_paid.value = moneyValue(record.amount_paid).toFixed(2);
  form.elements.remarks.value = record.remarks || record.notes || "";
  $("#remainingBalance").value = formatMoney(treatmentBalance(record));
  setText("#treatmentFormTitle", "Edit Treatment");
  $("#treatmentSubmitButton").textContent = "Update Treatment";
  openCrudDialog("#treatmentEditorDialog");
}

function searchPatientLabel(patient) {
  const contact = patient.mobile_number || patient.phone || patient.email || "No contact";
  return `${patient.name} | ${contact}`;
}

function searchPatientMatches() {
  const query = ($("#patientSearch")?.value || "").trim().toLowerCase();
  const patients = [...state.patients].sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  if (!query) return patients;
  return patients.filter((patient) => {
    const haystack = [
      searchPatientLabel(patient),
      patient.mobile_number,
      patient.phone,
      patient.email
    ].join(" ").toLowerCase();
    return haystack.includes(query);
  });
}

function patientDirectoryRowsHtml(patients) {
  return patients.length
    ? patients.map((patient) => {
      const editable = patient.source === "record";
      return `
        <tr class="${patient.id === state.selectedPatientId ? "is-selected" : ""}">
          <td>
            <strong>${escapeHtml(patient.name)}</strong>
            <div class="meta">${escapeHtml(patient.email || "No email")}</div>
          </td>
          <td>${escapeHtml(patient.mobile_number || patient.phone || "-")}</td>
          <td>${formatDate(patient.last_visit)}</td>
          <td><strong>${formatMoney(patient.total_balance)}</strong></td>
          <td>
            <div class="table-actions">
              <button class="ghost-button compact-button icon-action-button view-patient" data-id="${escapeHtml(patient.id)}" type="button" aria-label="View ${escapeHtml(patient.name)}" title="View patient" aria-haspopup="dialog" aria-controls="patientProfileDialog">${actionIcon("view")}</button>
              ${editable ? `<button class="secondary-button compact-button icon-action-button edit-patient" data-id="${escapeHtml(patient.id)}" type="button" aria-label="Edit ${escapeHtml(patient.name)}" title="Edit patient">${actionIcon("edit")}</button>` : ""}
              ${editable ? `<button class="danger-button compact-button icon-action-button delete-patient" data-id="${escapeHtml(patient.id)}" data-name="${escapeHtml(patient.name)}" type="button" aria-label="Delete ${escapeHtml(patient.name)}" title="Delete patient">${actionIcon("delete")}</button>` : ""}
            </div>
          </td>
        </tr>
      `;
    }).join("")
    : `<tr><td colspan="5" class="table-empty">No matching patient records.</td></tr>`;
}

function renderPatientSearch() {
  const input = $("#patientSearch");
  const options = $("#patientSearchOptions");
  if (!input || !options) return;

  const query = input.value.trim();
  const matches = searchPatientMatches();
  options.innerHTML = matches.slice(0, 25).map((patient) => (
    `<option value="${escapeHtml(searchPatientLabel(patient))}"></option>`
  )).join("");

  if (!state.selectedPatientId && state.patients[0]) {
    state.selectedPatientId = state.patients[0].id;
  }

  if (query) {
    const normalizedQuery = query.toLowerCase();
    const exactMatch = matches.find((patient) => (
      searchPatientLabel(patient).toLowerCase() === normalizedQuery
      || String(patient.name || "").toLowerCase() === normalizedQuery
      || String(patient.mobile_number || patient.phone || "").toLowerCase() === normalizedQuery
      || String(patient.email || "").toLowerCase() === normalizedQuery
    ));
    const selectedMatch = matches.find((patient) => patient.id === state.selectedPatientId);
    const patient = exactMatch || selectedMatch || matches[0] || null;
    state.selectedPatientId = patient ? patient.id : "";
  }

  const hint = query && !matches.length
    ? "No matching patient found."
    : query
      ? `${matches.length} matching patient${matches.length === 1 ? "" : "s"}`
      : `${state.patients.length} patient${state.patients.length === 1 ? "" : "s"}`;
  setText("#patientSearchHint", hint);

  const directory = $("#patientDirectoryRows");
  if (directory) directory.innerHTML = patientDirectoryRowsHtml(matches.slice(0, 5));

  const modalDirectory = $("#patientModalRows");
  if (modalDirectory) modalDirectory.innerHTML = patientDirectoryRowsHtml(matches);

  const hasMorePatients = matches.length > 5;
  $("#patientListFooter")?.classList.toggle("hidden", !hasMorePatients);
  setText("#patientListTitle", query ? "Matching Patients" : "All Patients");
}

function renderPatientProfile() {
  const patient = selectedPatient();
  const panel = $("#patientProfilePanel");
  if (!patient) {
    panel.classList.add("hidden");
    closeCrudDialog("#patientProfileDialog");
    const query = ($("#patientSearch")?.value || "").trim();
    setText("#patientSearchHint", query ? "No matching patient found." : "No patient records yet.");
    return;
  }

  state.selectedPatientId = patient.id;
  panel.classList.remove("hidden");
  setText("#patientProfileTitle", patient.name);
  const profileActions = $("#patientProfileActions");
  if (profileActions) {
    profileActions.innerHTML = `
        <button class="primary-button compact-button add-treatment" data-id="${escapeHtml(patient.id)}" type="button">+ Add Treatment</button>
        ${patient.source === "record" ? `
        <button class="secondary-button compact-button icon-action-button edit-patient" data-id="${escapeHtml(patient.id)}" type="button" aria-label="Edit ${escapeHtml(patient.name)}" title="Edit patient">${actionIcon("edit")}</button>
        <button class="danger-button compact-button icon-action-button delete-patient" data-id="${escapeHtml(patient.id)}" data-name="${escapeHtml(patient.name)}" type="button" aria-label="Delete ${escapeHtml(patient.name)}" title="Delete patient">${actionIcon("delete")}</button>
        ` : `<span class="meta">Patient login account</span>`}
      `;
  }
  $("#treatmentPatientId").value = patient.id;
  const selectedProcedure = $("#treatmentProcedure").value;
  $("#treatmentProcedure").innerHTML = procedureOptions(selectedProcedure);
  const records = patientRecords(patient.id).sort((a, b) => treatmentDate(a).localeCompare(treatmentDate(b)));
  const totals = patientTotals(patient.id);

  $("#patientProfileDetails").innerHTML = `
    <span><strong>${escapeHtml(patient.name)}</strong>Full Name</span>
    <span><strong>${formatDate(patient.birthdate)}</strong>Birthdate</span>
    <span><strong>${escapeHtml(patient.age || calculateAge(patient.birthdate) || "-")}</strong>Age</span>
    <span><strong>${escapeHtml(patient.address || "-")}</strong>Address</span>
    <span><strong>${escapeHtml(patient.nationality || "-")}</strong>Nationality</span>
    <span><strong>${escapeHtml(patient.occupation || "-")}</strong>Occupation</span>
    <span><strong>${escapeHtml(patient.phone_number || "-")}</strong>Phone Number</span>
    <span><strong>${escapeHtml(patient.mobile_number || patient.phone || "-")}</strong>Mobile Number</span>
    <span><strong>${escapeHtml(patient.email || "-")}</strong>Email</span>
  `;
  setText("#profileTotalCharged", formatMoney(totals.charged));
  setText("#profileTotalPaid", formatMoney(totals.paid));
  setText("#profileTotalBalance", formatMoney(totals.balance));

  $("#treatmentDirectory").innerHTML = records.length
    ? records.map((record) => `
      <tr data-entity-type="treatment" data-entity-id="${escapeHtml(record.id)}">
        <td>${formatDate(treatmentDate(record))}</td>
        <td>${escapeHtml(record.tooth_numbers || "-")}</td>
        <td>${escapeHtml(treatmentProcedure(record))}</td>
        <td>${formatMoney(record.amount_charged)}</td>
        <td>${formatMoney(record.amount_paid)}</td>
        <td>${formatMoney(treatmentBalance(record))}</td>
        <td>
          <div class="table-actions">
            <button class="secondary-button compact-button icon-action-button edit-treatment" data-id="${escapeHtml(record.id)}" type="button" aria-label="Edit treatment" title="Edit treatment">${actionIcon("edit")}</button>
            <button class="danger-button compact-button icon-action-button delete-treatment" data-id="${escapeHtml(record.id)}" type="button" aria-label="Delete treatment" title="Delete treatment">${actionIcon("delete")}</button>
            <button class="ghost-button compact-button icon-action-button view-treatment" data-id="${escapeHtml(record.id)}" type="button" aria-label="View treatment details" title="View treatment details">${actionIcon("view")}</button>
          </div>
        </td>
      </tr>
    `).join("")
    : `<tr><td colspan="7">No treatment records yet.</td></tr>`;
}

function openPatientProfile(patientId) {
  const patient = state.patients.find((item) => item.id === patientId);
  if (!patient) {
    showToast("Patient record not found.", "error");
    return;
  }
  closeCrudDialog("#patientListDialog");
  state.selectedPatientId = patient.id;
  renderPatientSearch();
  state.selectedPatientId = patient.id;
  renderPatientProfile();
  openCrudDialog("#patientProfileDialog");
}

function renderDentalServices() {
  const procedures = allProcedureOptions();
  if (!procedures.includes(state.selectedService)) {
    state.selectedService = procedures[0] || "Others";
  }
  $("#recordProcedure").innerHTML = procedureOptions($("#recordProcedure").value);
  $("#treatmentProcedure").innerHTML = procedureOptions($("#treatmentProcedure").value);

  $("#serviceCategoryList").innerHTML = procedures.map((procedure) => `
    <button class="${procedure === state.selectedService ? "active" : ""}" data-service-category="${escapeHtml(procedure)}" type="button">${escapeHtml(procedure)}</button>
  `).join("");
  setText("#selectedServiceTitle", state.selectedService);
  const rows = state.records
    .filter((record) => treatmentProcedure(record) === state.selectedService)
    .sort((a, b) => treatmentDate(b).localeCompare(treatmentDate(a)));
  $("#servicePatientRows").innerHTML = rows.length
    ? rows.map((record) => `
      <tr>
        <td>${escapeHtml(record.patient_name)}</td>
        <td>${formatDate(treatmentDate(record))}</td>
        <td>${escapeHtml(record.doctor_name || "Dentist")}</td>
        <td>${statusLabel(paymentStatus(record))}</td>
      </tr>
    `).join("")
    : `<tr><td colspan="4">No patients have received this service yet.</td></tr>`;
}

function renderPatientManagement() {
  renderDentalServices();
  renderPatientSearch();
  renderPatientProfile();
}

function renderDoctorLists() {
  renderPatientManagement();

  $("#doctorServiceList").innerHTML = state.services.length
    ? state.services.map((service) => `
      <tr>
        <td><strong>${escapeHtml(service.name)}</strong></td>
        <td>${escapeHtml(service.description)}</td>
        <td><button class="danger-button compact-button icon-action-button delete-service" data-id="${escapeHtml(service.id)}" data-name="${escapeHtml(service.name)}" type="button" aria-label="Delete ${escapeHtml(service.name)}" title="Delete service">${actionIcon("delete")}</button></td>
      </tr>
    `).join("")
    : `<tr><td colspan="3" class="table-empty">No services yet.</td></tr>`;

  $("#doctorPromoList").innerHTML = state.promos.length
    ? state.promos.map((promo) => `
      <tr>
        <td><strong>${escapeHtml(promo.title)}</strong></td>
        <td>${escapeHtml(promo.description)}</td>
        <td><button class="danger-button compact-button icon-action-button delete-promo" data-id="${escapeHtml(promo.id)}" data-name="${escapeHtml(promo.title)}" type="button" aria-label="Delete ${escapeHtml(promo.title)}" title="Delete promo">${actionIcon("delete")}</button></td>
      </tr>
    `).join("")
    : `<tr><td colspan="3" class="table-empty">No promos yet.</td></tr>`;
}

function renderDoctorDashboard() {
  updateUserProfile("doctor", "Doctor");
  setText("#doctorPatientCount", state.patients.length);
  setText("#doctorAppointmentCount", state.appointments.length);
  setText("#doctorReviewCount", state.feedback.length);
  setText("#doctorPendingCount", countStatus("pending"));
  setText("#doctorCompletedCount", countStatus("completed"));
  setText("#doctorCancelledCount", countStatus("cancelled"));
  renderNotifications();
  renderDoctorOverviewWidgets();

  const rows = doctorAppointmentRows();
  const overviewRows = $("#doctorAppointments");
  if (overviewRows) overviewRows.innerHTML = rows;
  $("#doctorScheduleRows").innerHTML = rows;
  renderAvailabilityRows();

  $("#recordPatient").innerHTML = state.patients.length
    ? state.patients.map((patient) => `<option value="${escapeHtml(patient.id)}">${escapeHtml(patient.name)}</option>`).join("")
    : `<option value="">No patients yet</option>`;
  renderRecordAppointmentOptions();
  renderDoctorRecords();
  renderDoctorReviews();
  renderDoctorLists();
  renderMessages("doctor");

  $$(".status-select").forEach((select) => {
    select.addEventListener("change", () => updateAppointmentStatus(select.dataset.id, select.value));
  });
  $$(".delete-service").forEach((button) => {
    button.addEventListener("click", () => deleteService(button.dataset.id, button.dataset.name));
  });
  $$(".delete-promo").forEach((button) => {
    button.addEventListener("click", () => deletePromo(button.dataset.id, button.dataset.name));
  });
  $$(".delete-feedback").forEach((button) => {
    button.addEventListener("click", () => deleteFeedback(button.dataset.id, button.dataset.name));
  });
}

async function updateAppointmentStatus(id, status) {
  try {
    await api("/api/appointments", {
      method: "PATCH",
      body: JSON.stringify({ id, status })
    });
    showToast("Appointment updated.");
    if (page === "doctor") {
      await loadDoctorData();
    } else {
      await loadPatientData();
    }
  } catch (error) {
    showToast(error.message, "error");
    if (page === "doctor") {
      await loadDoctorData();
    } else {
      await loadPatientData();
    }
  }
}

async function submitMessage(prefix, event) {
  event.preventDefault();
  const form = event.currentTarget;
  const contactId = $(`#${prefix}MessageContact`).value;
  const payload = validatedPayload(form);
  if (!payload) return;
  payload.recipient_id = contactId;
  try {
    await api("/api/messages", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    form.reset();
    showToast("Message sent.");
    if (page === "doctor") {
      await loadDoctorData();
      showPanel("doctorMessages");
    } else {
      await loadPatientData();
      showPanel("patientMessages");
    }
  } catch (error) {
    showToast(error.message, "error");
  }
}

function bindProfileImageInput(prefix) {
  const input = $(`#${prefix}ProfileImageFile`);
  const hidden = $(`#${prefix}EditProfileImage`);
  if (!input || !hidden) return;
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      showToast("Use a PNG, JPG, or WEBP image.", "error");
      input.value = "";
      return;
    }
    if (file.size > 2_000_000) {
      showToast("Profile picture must be under 2 MB.", "error");
      input.value = "";
      return;
    }
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      hidden.value = reader.result;
      setAvatar(`#${prefix}ProfileInitials`, state.user.name, reader.result);
      setAvatar(`#${prefix}SidebarInitials`, state.user.name, reader.result);
    });
    reader.readAsDataURL(file);
  });
}

function confirmDelete(label) {
  return window.confirm(`Delete ${label}? This cannot be undone.`);
}

async function deleteResource(path, id, label, successMessage) {
  if (!id) {
    showToast("Choose an item to delete.", "error");
    return;
  }
  if (!confirmDelete(label)) return;
  try {
    await api(path, {
      method: "DELETE",
      body: JSON.stringify({ id })
    });
    showToast(successMessage);
    await loadDoctorData();
    showPanel("doctorSettings");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function deletePatient(id, name) {
  if (!id) return;
  if (!confirmDelete(`${name || "this patient record"} and all related dental records`)) return;
  try {
    await api("/api/patients", {
      method: "DELETE",
      body: JSON.stringify({ id })
    });
    closeCrudDialog("#patientProfileDialog");
    showToast("Patient record deleted.");
    await loadDoctorData();
    showPanel("doctorPatients");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function viewTreatmentDetails(id) {
  const record = state.records.find((item) => item.id === id);
  if (!record) return;
  window.alert([
    `Patient: ${record.patient_name || "Patient"}`,
    `Date: ${formatDate(treatmentDate(record))}`,
    `Tooth No./s: ${record.tooth_numbers || "-"}`,
    `Procedure: ${treatmentProcedure(record)}`,
    `Amount Charged: ${formatMoney(record.amount_charged)}`,
    `Amount Paid: ${formatMoney(record.amount_paid)}`,
    `Balance: ${formatMoney(treatmentBalance(record))}`,
    `Status: ${paymentStatus(record)}`,
    `Dentist: ${record.doctor_name || "Dentist"}`,
    `Remarks: ${record.remarks || record.notes || "-"}`
  ].join("\n"));
}

async function deleteTreatment(id) {
  if (!id) return;
  const record = state.records.find((item) => item.id === id);
  if (!confirmDelete(`${treatmentProcedure(record || {})} treatment record`)) return;
  try {
    await api("/api/records", {
      method: "DELETE",
      body: JSON.stringify({ id })
    });
    showToast("Treatment record deleted.");
    await loadDoctorData();
    showPanel("doctorPatients");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function deleteService(id, name) {
  deleteResource("/api/services", id, name || "this service", "Service deleted.");
}

function deletePromo(id, name) {
  deleteResource("/api/promos", id, name || "this promo", "Promo deleted.");
}

function deleteFeedback(id, name) {
  deleteResource("/api/feedback", id, `${name || "this"} feedback`, "Feedback deleted.");
}

async function submitPatient(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  payload.name = [payload.first_name, payload.middle_name, payload.last_name]
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .join(" ");
  const isEdit = Boolean(payload.id);
  try {
    const data = await api("/api/patients", {
      method: isEdit ? "PATCH" : "POST",
      body: JSON.stringify(payload)
    });
    const savedPatient = data.patient || null;
    if (savedPatient?.id) state.selectedPatientId = savedPatient.id;
    form.reset();
    closeCrudDialog("#patientEditorDialog");
    showToast(isEdit ? "Patient record updated." : "Patient record saved.");
    await loadDoctorData();
    resetPatientForm();
    showPanel("doctorPatients");
    if (!isEdit && savedPatient?.id) {
      state.selectedPatientId = savedPatient.id;
      setText("#savedPatientName", savedPatient.name || "The patient");
      openCrudDialog("#patientTreatmentPrompt");
    }
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitRecord(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  payload.procedure = String(payload.procedure || "").trim();
  payload.treatment = payload.procedure;
  payload.diagnosis = payload.diagnosis || payload.procedure;
  try {
    const data = await api("/api/records", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    if (data.record) upsertRecord(data.record);
    state.selectedPatientId = data.record?.patient_id || payload.patient_id || state.selectedPatientId;
    form.reset();
    form.elements.treatment_date.value = todayIso();
    closeCrudDialog("#recordEditorDialog");
    updateTreatmentBalance("record");
    renderDoctorRecords();
    renderPatientManagement();
    showToast("Dental record saved.");
    loadDoctorData().catch((error) => showToast(error.message, "error"));
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitTreatment(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  payload.patient_id = payload.patient_id || state.selectedPatientId;
  payload.procedure = String(payload.procedure || "").trim();
  payload.treatment = payload.procedure;
  payload.diagnosis = payload.diagnosis || payload.procedure;
  if (!payload.patient_id) {
    showToast("Choose a patient before saving a treatment.", "error");
    return;
  }
  const isEdit = Boolean(payload.id);
  try {
    const data = await api("/api/records", {
      method: isEdit ? "PATCH" : "POST",
      body: JSON.stringify(payload)
    });
    if (data.record) upsertRecord(data.record);
    state.selectedPatientId = data.record?.patient_id || payload.patient_id;
    form.reset();
    closeCrudDialog("#treatmentEditorDialog");
    resetTreatmentForm();
    renderDoctorRecords();
    renderPatientManagement();
    showPanel("doctorPatients");
    showToast(isEdit ? "Treatment record updated." : "Treatment record saved.");
    loadDoctorData()
      .then(() => showPanel("doctorPatients"))
      .catch((error) => showToast(error.message, "error"));
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitAvailability(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  if (!selectedAvailabilityDates.size) {
    showToast("Select at least one available date.", "error");
    return;
  }
  const [inHour, inMinute] = String(payload.time_in).split(":").map(Number);
  const [outHour, outMinute] = String(payload.time_out).split(":").map(Number);
  if ((outHour * 60) + outMinute <= (inHour * 60) + inMinute) {
    showToast("Time out must be later than time in.", "error");
    return;
  }
  try {
    const data = await api("/api/availability", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    clearAvailabilityDates();
    const createdCount = Number(data.created_count || 0);
    const skippedCount = Number(data.skipped_count || 0);
    const skippedMessage = skippedCount ? ` ${skippedCount} existing ${skippedCount === 1 ? "slot was" : "slots were"} skipped.` : "";
    showToast(`${createdCount} ${createdCount === 1 ? "time slot" : "time slots"} created.${skippedMessage}`);
    await loadDoctorData();
    showPanel("doctorSchedule");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitAvailabilityEditor(event) {
  event.preventDefault();
  const payload = validatedPayload(event.currentTarget);
  if (!payload) return;
  try {
    await api("/api/availability", {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
    closeCrudDialog("#availabilityEditorDialog");
    showToast("Availability updated.");
    await loadDoctorData();
    showPanel("doctorSchedule");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitService(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  try {
    await api("/api/services", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    form.reset();
    showToast("Service saved.");
    await loadDoctorData();
    showPanel("doctorSettings");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitPromo(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  try {
    await api("/api/promos", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    form.reset();
    showToast("Promo saved.");
    await loadDoctorData();
    showPanel("doctorSettings");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function submitFeedbackEdit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = validatedPayload(form);
  if (!payload) return;
  try {
    await api("/api/feedback", {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
    showToast("Feedback updated.");
    await loadDoctorData();
    showPanel("doctorSettings");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function bindCommonEvents() {
  $$(".logout-trigger").forEach((button) => {
    button.addEventListener("click", logout);
  });
  $$("[data-panel-target]").forEach((button) => {
    button.addEventListener("click", () => showPanel(button.dataset.panelTarget));
  });
  $$(".book-link").forEach((button) => {
    button.addEventListener("click", () => {
      if (page === "patient") {
        openPatientAppointmentDialog();
      } else {
        window.location.href = "index.html#appointmentForm";
      }
    });
  });
  const notificationCenter = $(".notification-center");
  const notificationButton = $("#notificationButton");
  const notificationPanel = $("#notificationPanel");
  notificationButton?.addEventListener("click", () => {
    setNotificationPanelOpen(notificationButton.getAttribute("aria-expanded") !== "true");
  });
  $("#notificationReadAll")?.addEventListener("click", () => markNotificationsRead());
  $("#notificationList")?.addEventListener("click", async (event) => {
    const itemButton = event.target.closest("[data-notification-id]");
    if (!itemButton) return;
    const notification = state.notifications.find((item) => item.id === itemButton.dataset.notificationId);
    if (notification && !notification.is_read) {
      await markNotificationsRead(notification.id);
    }
    setNotificationPanelOpen(false);
    openNotificationTarget(notification);
  });
  document.addEventListener("click", (event) => {
    if (!notificationPanel || notificationPanel.classList.contains("hidden")) return;
    if (!notificationCenter?.contains(event.target)) setNotificationPanelOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setNotificationPanelOpen(false);
  });
}

function bindPatientEvents() {
  bindProfileImageInput("patient");
  $("#patientProfileForm").addEventListener("submit", submitPatientProfile);
  $("#patientMessageContact").addEventListener("change", () => renderMessages("patient"));
  $("#patientMessageForm").addEventListener("submit", (event) => submitMessage("patient", event));
  $("#patientAppointmentForm").addEventListener("submit", submitPatientAppointment);
  $("#patientAppointmentDate").addEventListener("change", renderPatientAppointmentTimeSlots);
  $("#patientBookAgain").addEventListener("click", openPatientAppointmentDialog);
  ["closePatientAppointmentDialog", "cancelPatientAppointmentDialog"].forEach((id) => {
    $(`#${id}`).addEventListener("click", () => closeCrudDialog("#patientAppointmentDialog"));
  });
  const appointmentDialog = $("#patientAppointmentDialog");
  appointmentDialog.addEventListener("click", (event) => {
    if (event.target === appointmentDialog) closeCrudDialog("#patientAppointmentDialog");
  });
  renderPatientAppointmentTimeSlots();
}

function focusDoctorTool(selector) {
  showPanel("doctorSettings");
  window.setTimeout(() => {
    const target = $(selector);
    if (target) target.focus();
  }, 100);
}

function bindDoctorEvents() {
  bindProfileImageInput("doctor");
  $("#doctorProfileForm").addEventListener("submit", submitDoctorProfile);
  $("#doctorMessageContact").addEventListener("change", () => renderMessages("doctor"));
  $("#doctorMessageForm").addEventListener("submit", (event) => submitMessage("doctor", event));
  $("#patientForm").addEventListener("submit", submitPatient);
  $("#recordForm").addEventListener("submit", submitRecord);
  $("#treatmentForm").addEventListener("submit", submitTreatment);
  $("#availabilityForm").addEventListener("submit", submitAvailability);
  $("#availabilityEditorForm").addEventListener("submit", submitAvailabilityEditor);
  $("#serviceForm").addEventListener("submit", submitService);
  $("#promoForm").addEventListener("submit", submitPromo);
  $("#feedbackEditForm").addEventListener("submit", submitFeedbackEdit);
  $("#recordPatient").addEventListener("change", renderRecordAppointmentOptions);
  $("#patientBirthdate").addEventListener("input", updatePatientAge);
  $("#resetPatientForm").addEventListener("click", () => {
    resetPatientForm();
    openCrudDialog("#patientEditorDialog");
  });
  ["closePatientDialog", "cancelPatientDialog"].forEach((id) => {
    $(`#${id}`).addEventListener("click", () => closeCrudDialog("#patientEditorDialog"));
  });
  ["closeTreatmentDialog", "cancelTreatmentDialog"].forEach((id) => {
    $(`#${id}`).addEventListener("click", () => closeCrudDialog("#treatmentEditorDialog"));
  });
  ["patientEditorDialog", "treatmentEditorDialog", "recordEditorDialog"].forEach((id) => {
    $(`#${id}`).addEventListener("click", (event) => {
      if (event.target === event.currentTarget) closeCrudDialog(`#${id}`);
    });
  });
  $("#patientSearch").addEventListener("input", () => {
    renderPatientSearch();
    renderPatientProfile();
  });
  $("#patientSearch").addEventListener("change", () => {
    renderPatientSearch();
    renderPatientProfile();
  });
  $("#portalGlobalSearch")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    showPanel("doctorPatients");
    setValue("#patientSearch", event.currentTarget.value.trim());
    renderPatientSearch();
    renderPatientProfile();
    $("#patientSearch")?.focus();
  });
  ["closePatientProfileDialog"].forEach((id) => {
    $(`#${id}`).addEventListener("click", () => closeCrudDialog("#patientProfileDialog"));
  });
  $("#patientProfileDialog").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeCrudDialog("#patientProfileDialog");
  });
  $("#openPatientListDialog").addEventListener("click", () => openCrudDialog("#patientListDialog"));
  ["closePatientListDialog", "donePatientListDialog"].forEach((id) => {
    $(`#${id}`).addEventListener("click", () => closeCrudDialog("#patientListDialog"));
  });
  $("#patientListDialog").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeCrudDialog("#patientListDialog");
  });
  ["amountCharged", "amountPaid"].forEach((id) => {
    $(`#${id}`).addEventListener("input", () => updateTreatmentBalance());
  });
  ["recordAmountCharged", "recordAmountPaid"].forEach((id) => {
    $(`#${id}`).addEventListener("input", () => updateTreatmentBalance("record"));
  });
  $("#doctorPatients").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || !$("#doctorPatients").contains(button)) return;
    if (button.matches(".view-patient")) {
      openPatientProfile(button.dataset.id);
    }
    if (button.matches(".edit-patient")) editPatientForm(button.dataset.id);
    if (button.matches(".delete-patient")) deletePatient(button.dataset.id, button.dataset.name);
    if (button.matches(".add-treatment")) {
      state.selectedPatientId = button.dataset.id;
      resetTreatmentForm();
      openCrudDialog("#treatmentEditorDialog");
    }
    if (button.matches(".edit-treatment")) editTreatmentForm(button.dataset.id);
    if (button.matches(".delete-treatment")) deleteTreatment(button.dataset.id);
    if (button.matches(".view-treatment")) viewTreatmentDetails(button.dataset.id);
    if (button.dataset.serviceCategory) {
      state.selectedService = button.dataset.serviceCategory;
      renderDentalServices();
    }
  });
  $("#feedbackSelect").addEventListener("change", populateFeedbackForm);
  $("#refreshDoctorData").addEventListener("click", loadDoctorData);
  $("#refreshScheduleData").addEventListener("click", loadDoctorData);
  $("#dashboardRangeStart")?.addEventListener("change", (event) => {
    if (!event.currentTarget.value) return;
    state.selectedOverviewDate = event.currentTarget.value;
    renderDoctorDayStrip();
    renderDoctorDailySchedule();
  });
  $("#dashboardRangeEnd")?.addEventListener("change", (event) => {
    const start = $("#dashboardRangeStart")?.value;
    if (start && event.currentTarget.value && event.currentTarget.value < start) {
      event.currentTarget.value = start;
    }
  });
  $("#availabilityMonth").addEventListener("change", () => {
    selectedAvailabilityDates.clear();
    renderAvailabilityCalendar();
  });
  $("#availabilityCalendar").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-availability-date]");
    if (!button || button.disabled) return;
    const dateValue = button.dataset.availabilityDate;
    if (selectedAvailabilityDates.has(dateValue)) {
      selectedAvailabilityDates.delete(dateValue);
    } else {
      selectedAvailabilityDates.add(dateValue);
    }
    renderAvailabilityCalendar();
  });
  $("#clearAvailabilityDates").addEventListener("click", clearAvailabilityDates);
  $("#openAvailabilityListDialog").addEventListener("click", () => openCrudDialog("#availabilityListDialog"));
  ["closeAvailabilityListDialog", "doneAvailabilityListDialog"].forEach((id) => {
    $(`#${id}`).addEventListener("click", () => closeCrudDialog("#availabilityListDialog"));
  });
  $("#availabilityListDialog").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeCrudDialog("#availabilityListDialog");
  });
  ["closeAvailabilityEditor", "cancelAvailabilityEditor"].forEach((id) => {
    $(`#${id}`).addEventListener("click", () => closeCrudDialog("#availabilityEditorDialog"));
  });
  $("#availabilityEditorDialog").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeCrudDialog("#availabilityEditorDialog");
  });
  $("#doctorSchedule").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.matches(".edit-availability")) editAvailability(button.dataset.id);
    if (button.matches(".delete-availability")) deleteAvailability(button.dataset.id);
  });
  $("#doctorOverview").addEventListener("click", (event) => {
    const dateButton = event.target.closest("[data-overview-date]");
    if (dateButton) {
      state.selectedOverviewDate = dateButton.dataset.overviewDate;
      renderDoctorDayStrip();
      renderDoctorDailySchedule();
      return;
    }
    const decisionButton = event.target.closest(".appointment-decision");
    if (decisionButton) {
      decisionButton.disabled = true;
      updateAppointmentStatus(decisionButton.dataset.id, decisionButton.dataset.status);
      return;
    }
    const treatmentTile = event.target.closest(".treatment-tile");
    if (treatmentTile) {
      state.selectedService = treatmentTile.dataset.serviceCategory;
      showPanel("doctorPatients");
      renderDentalServices();
    }
  });
  $("#openRecordDialog")?.addEventListener("click", () => openCrudDialog("#recordEditorDialog"));
  ["closeRecordDialog", "cancelRecordDialog"].forEach((id) => {
    $(`#${id}`).addEventListener("click", () => closeCrudDialog("#recordEditorDialog"));
  });
  $("#actionAddPatient")?.addEventListener("click", () => {
    showPanel("doctorPatients");
    resetPatientForm();
    openCrudDialog("#patientEditorDialog");
  });
  ["closePatientTreatmentPrompt", "skipPatientTreatment"].forEach((id) => {
    $(`#${id}`).addEventListener("click", () => closeCrudDialog("#patientTreatmentPrompt"));
  });
  $("#patientTreatmentPrompt").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeCrudDialog("#patientTreatmentPrompt");
  });
  $("#confirmPatientTreatment").addEventListener("click", () => {
    const patientId = state.selectedPatientId;
    closeCrudDialog("#patientTreatmentPrompt");
    if (!patientId) {
      showToast("The saved patient could not be selected.", "error");
      return;
    }
    showPanel("doctorPatients");
    openPatientProfile(patientId);
    resetTreatmentForm();
    openCrudDialog("#treatmentEditorDialog");
  });
  $("#actionManageAvailability")?.addEventListener("click", () => {
    showPanel("doctorSchedule");
    resetAvailabilityForm();
    $("#availabilityMonth").focus();
  });
  $("#actionAddService")?.addEventListener("click", () => focusDoctorTool("#serviceForm input[name='name']"));
  $("#actionAddPromo")?.addEventListener("click", () => focusDoctorTool("#promoForm input[name='title']"));
  $("#actionEditFeedback")?.addEventListener("click", () => focusDoctorTool("#feedbackMessage"));
  $("#deleteFeedbackButton").addEventListener("click", () => {
    const item = state.feedback.find((feedback) => feedback.id === $("#feedbackSelect").value);
    deleteFeedback(item?.id, item?.name);
  });
  $("#recordForm").elements.treatment_date.value = todayIso();
  $("#treatmentForm").elements.treatment_date.value = todayIso();
  resetAvailabilityForm();
  updateTreatmentBalance();
  updateTreatmentBalance("record");
}

function setMinimumDates() {
  const today = todayIso();
  $$('input[data-min-today="true"], input[name="next_visit"]').forEach((input) => {
    input.min = today;
  });
  $$('input[name="birthdate"], input[name="treatment_date"]').forEach((input) => {
    input.max = today;
  });
}

async function boot() {
  consumeQueuedToast();
  bindCommonEvents();
  setMinimumDates();
  try {
    const allowed = await requireDashboardRole();
    if (!allowed) return;
    if (page === "doctor") {
      bindDoctorEvents();
      await loadDoctorData();
    } else {
      bindPatientEvents();
      await loadPatientData();
    }
    startNotificationPolling();
  } catch (error) {
    showToast(error.message, "error");
  }
}

document.addEventListener("DOMContentLoaded", boot);
