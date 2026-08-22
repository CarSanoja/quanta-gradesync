const DAY_MS = 86400000;

export function prettyName(studentId) {
  return String(studentId)
    .split(/[-_.]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ") || String(studentId);
}

export function prettySubject(subject) {
  const plain = String(subject || "").replace(/[-_]+/g, " ").trim();
  return plain ? plain[0].toUpperCase() + plain.slice(1) : "";
}

export function firstName(fullName) {
  return String(fullName || "").trim().split(/\s+/)[0] || String(fullName || "");
}

export function plural(count, one, many) {
  return count === 1 ? one : many;
}

export function fmt(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }
  return String(Math.round(Number(value) * 100) / 100);
}

export function pointsOf(score, max) {
  return max === null || max === undefined
    ? `${fmt(score)} points`
    : `${fmt(score)} of ${fmt(max)}`;
}

function clockOf(then) {
  return then
    .toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    .toLowerCase();
}

function sameDay(left, right) {
  return left.toDateString() === right.toDateString();
}

export function whenSent(value) {
  const then = new Date(value);
  if (!value || Number.isNaN(then.getTime())) {
    return "";
  }
  const now = new Date();
  const yesterday = new Date(now.getTime() - DAY_MS);
  if (sameDay(then, now)) {
    return `today at ${clockOf(then)}`;
  }
  if (sameDay(then, yesterday)) {
    return `yesterday at ${clockOf(then)}`;
  }
  const day = then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `on ${day} at ${clockOf(then)}`;
}

export function timeAgo(value) {
  const then = new Date(value);
  if (!value || Number.isNaN(then.getTime())) {
    return "";
  }
  const minutes = Math.round((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours === 1 ? "an hour ago" : `${hours} hours ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function parseLot(lotCode) {
  const parts = String(lotCode || "").split("_");
  if (parts.length !== 4) {
    return null;
  }
  return {
    year: parts[0],
    subject: prettyName(parts[1]),
    classId: parts[2],
    assessment: prettyName(parts[3]),
  };
}

export function examCount(count) {
  return `${count} ${plural(count, "exam", "exams")}`;
}
