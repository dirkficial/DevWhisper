/**
 * ui.js — DOM references and shared UI helpers.
 *
 * All direct DOM interaction is centralized here so the other modules
 * stay framework-agnostic and easy to migrate to React later.
 */

export const startBtn  = document.getElementById("startBtn");
export const stopBtn   = document.getElementById("stopBtn");
export const statusDot = document.getElementById("statusDot");
export const statusText = document.getElementById("statusText");
export const logEl     = document.getElementById("log");

const STATUS_LABELS = {
  idle:       "Idle",
  connecting: "Connecting…",
  streaming:  "Streaming",
  stopped:    "Stopped",
  error:      "Error",
};

/**
 * Updates the status badge (dot colour + label).
 * @param {"idle"|"connecting"|"streaming"|"stopped"|"error"} state
 */
export function setStatus(state) {
  statusDot.dataset.status = state;
  statusText.textContent = STATUS_LABELS[state] ?? state;
}

/**
 * Appends a line to the session log panel.
 * @param {string} message
 * @param {"info"|"ok"|"warn"|"err"|""} [type=""]
 */
export function log(message, type = "") {
  const ts = new Date().toLocaleTimeString("en-US", { hour12: false });

  const tsSpan = document.createElement("span");
  tsSpan.className = "log-ts";
  tsSpan.textContent = ts;

  const msgSpan = document.createElement("span");
  msgSpan.className = "log-msg";
  msgSpan.textContent = message;

  const entry = document.createElement("div");
  entry.className = `log-entry ${type}`;
  entry.appendChild(tsSpan);
  entry.appendChild(msgSpan);

  logEl.appendChild(entry);
  logEl.scrollTop = logEl.scrollHeight;
}
