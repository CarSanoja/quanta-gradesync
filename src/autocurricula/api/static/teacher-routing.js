import { currentReview, screenFor, state } from "/teacher/assets/teacher-state.js";

function put(url, key, value) {
  if (value) {
    url.searchParams.set(key, value);
  } else {
    url.searchParams.delete(key);
  }
}

export function syncAddress(push) {
  const url = new URL(window.location.href);
  put(url, "batch", state.lotCode);
  const review = state.screen === "review" ? currentReview() : null;
  if (review) {
    url.searchParams.set("review", review.student_id);
  } else {
    url.searchParams.delete("review");
  }
  if (state.screen === "grades") {
    url.searchParams.set("grades", state.queries.grades || "1");
  } else {
    url.searchParams.delete("grades");
  }
  if (state.screen === "held") {
    url.searchParams.set("needs", "1");
  } else {
    url.searchParams.delete("needs");
  }
  if (state.screen === "home") {
    url.searchParams.set("send", "1");
  } else {
    url.searchParams.delete("send");
  }
  if (state.queries.band && state.screen !== "grades" && state.screen !== "review") {
    url.searchParams.set("show", state.queries.band);
  } else {
    url.searchParams.delete("show");
  }
  if (url.href === window.location.href) {
    return;
  }
  window.history[push ? "pushState" : "replaceState"]({}, "", url);
}

export function readAddress() {
  const route = new URLSearchParams(window.location.search);
  state.lotCode = route.get("batch") || "";
  state.following = Boolean(state.lotCode);
  state.requestedReview = route.get("review") || "";
  state.queries.grades = route.get("grades") === "1" ? "" : route.get("grades") || "";
  state.queries.band = route.get("show") || "";
  state.screen = screenFor(route);
  state.polls = 0;
}
