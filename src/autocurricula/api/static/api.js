const TOKEN_KEY = "gradesync.console.token";

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `request failed with status ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(value) {
  sessionStorage.setItem(TOKEN_KEY, value.trim());
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

async function detailOf(response) {
  try {
    const body = await response.json();
    if (body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch (error) {
    return response.statusText;
  }
  return response.statusText;
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response));
  }
  return response;
}

export async function getJson(path) {
  const response = await request(path);
  return response.json();
}

export async function postJson(path) {
  const response = await request(path, { method: "POST" });
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
  pageImage: (reviewId, index) =>
    `/review/${encodeURIComponent(reviewId)}/page-image?index=${index}`,
  optimizer: () => "/optimizer/report",
  fleetRegistry: () => "/fleet/registry",
  sisRecords: (jobId, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (jobId) {
      params.set("job_id", jobId);
    }
    return `/sis/records?${params}`;
  },
  trace: (jobId) => `/jobs/${encodeURIComponent(jobId)}/trace`,
  ingestExam: () => "/ingest/exam",
  sampleBatch: () => "/ingest/sample-batch",
};
