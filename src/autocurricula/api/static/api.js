const TOKEN_KEY = "gradesync.console.token";

export class ApiError extends Error {
  constructor(status, detail, body) {
    super(detail || `request failed with status ${status}`);
    this.status = status;
    this.detail = detail;
    this.body = body === undefined ? null : body;
  }
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(value) {
  localStorage.setItem(TOKEN_KEY, value.trim());
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function failureOf(response) {
  let body = null;
  try {
    body = await response.json();
  } catch (error) {
    body = null;
  }
  const detail = body && typeof body.detail === "string" ? body.detail : response.statusText;
  return new ApiError(response.status, detail, body);
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    throw await failureOf(response);
  }
  return response;
}

export async function getJson(path) {
  const response = await request(path);
  return response.json();
}

export async function postJson(path, body) {
  const options = { method: "POST" };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const response = await request(path, options);
  return response.json();
}

export async function postForm(path, formData) {
  const headers = new Headers();
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(path, { method: "POST", body: formData, headers });
  let body = null;
  try {
    body = await response.json();
  } catch (error) {
    body = null;
  }
  return { status: response.status, ok: response.ok, body };
}

export async function getObjectUrl(path) {
  const response = await request(path);
  return URL.createObjectURL(await response.blob());
}

export async function readiness() {
  const response = await fetch("/readyz");
  return response.json();
}

export const endpoints = {
  jobs: () => "/jobs",
  job: (jobId) => `/jobs/${encodeURIComponent(jobId)}`,
  pending: () => "/review/pending",
  approve: (reviewId) => `/review/${encodeURIComponent(reviewId)}/approve`,
  dismiss: (reviewId) => `/review/${encodeURIComponent(reviewId)}/dismiss`,
  bulkApprove: () => "/review/bulk-approve",
  teacherSummary: () => "/teacher/summary",
  pageImage: (reviewId, index) =>
    `/review/${encodeURIComponent(reviewId)}/page-image?index=${index}`,
  optimizer: () => "/optimizer/report",
  fleetRegistry: () => "/fleet/registry",
  sisRecords: (jobId, limit = 50, studentId = "") => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (jobId) {
      params.set("job_id", jobId);
    }
    if (studentId) {
      params.set("student_id", studentId);
    }
    return `/sis/records?${params}`;
  },
  trace: (jobId) => `/jobs/${encodeURIComponent(jobId)}/trace`,
  live: (jobId, after) =>
    `/jobs/${encodeURIComponent(jobId)}/live?after=${after}&limit=500`,
  ingestExam: () => "/ingest/exam",
  sampleBatch: () => "/ingest/sample-batch",
};
