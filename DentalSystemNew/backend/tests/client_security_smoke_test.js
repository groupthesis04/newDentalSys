"use strict";

global.window = {};
global.FormData = class {
  constructor(form) {
    this.values = form.values;
  }

  entries() {
    return Object.entries(this.values)[Symbol.iterator]();
  }
};

require("../../frontend/security.js");

function form(id, values, elements = {}) {
  return {
    id,
    values,
    elements,
    checkValidity: () => true,
    reportValidity: () => undefined
  };
}

function mustThrow(label, callback) {
  try {
    callback();
  } catch {
    return;
  }
  throw new Error(`${label} did not fail validation`);
}

const valid = window.DRMSSecurity.formPayload(form("registerForm", {
  name: "  Security   Patient  ",
  email: "security@example.test",
  password: "StrongPass123!",
  role: "patient",
  _website: ""
}));

if (valid.name !== "Security Patient") {
  throw new Error("text normalization failed");
}

const future = new Date();
future.setDate(future.getDate() + 30);
const futureDate = [
  future.getFullYear(),
  String(future.getMonth() + 1).padStart(2, "0"),
  String(future.getDate()).padStart(2, "0")
].join("-");
const validAppointment = window.DRMSSecurity.formPayload(form("patientAppointmentForm", {
  doctor: "Dr. Maria Santos",
  service: "Oral Prophylaxis",
  date: futureDate,
  time: "09:30",
  _website: ""
}));

if (validAppointment.date !== futureDate) {
  throw new Error("valid local appointment date was rejected");
}

mustThrow("invalid calendar date", () => window.DRMSSecurity.formPayload(form("patientAppointmentForm", {
  doctor: "Dr. Maria Santos",
  service: "Oral Prophylaxis",
  date: "2026-02-30",
  time: "09:30",
  _website: ""
})));

mustThrow("weak password", () => window.DRMSSecurity.formPayload(form("registerForm", {
  name: "Security Patient",
  email: "security@example.test",
  password: "weakpassword",
  role: "patient",
  _website: ""
})));

mustThrow("overpayment", () => window.DRMSSecurity.formPayload(form("treatmentForm", {
  patient_id: "pat_test",
  treatment_date: new Date().toISOString().slice(0, 10),
  tooth_numbers: "11, 12",
  procedure: "Oral Prophylaxis",
  amount_charged: "500",
  amount_paid: "600",
  _website: ""
})));

mustThrow("honeypot", () => window.DRMSSecurity.formPayload(form("feedbackForm", {
  name: "Bot",
  rating: "5",
  message: "Automated feedback message",
  _website: "https://spam.invalid"
})));

console.log("Client security smoke checks passed.");
