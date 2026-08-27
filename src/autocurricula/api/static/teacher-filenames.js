export const ALLOWED_SUFFIXES = new Set([".jpg", ".jpeg", ".png", ".pdf", ".heic"]);

const CAMERA_PATTERNS = [
  /^(img|dsc|dscn|dscf|pxl|photo|image|foto|scan|mvimg)[\s._-]*\d/i,
  /^whats\s?app[\s._-]*image/i,
  /^screen\s?shot/i,
  /^\d+$/,
  /^[^a-z]+$/i,
];

const PAGE_MARKER = /^(.+?)[\s._-]*(?:p|pg|page)[\s._-]*(\d{1,3})$/i;
const COPY_MARKER = /^(.+?)\s*\((\d{1,3})\)$/;
const BARE_NUMBER = /^(.+?)[\s._-]+(\d{1,3})$/;
const MAX_IMPLICIT_PAGE_GROUP = 3;

export function fileStem(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

export function fileSuffix(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot).toLowerCase() : "";
}

export function slugify(value) {
  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "");
}

export function looksLikeCamera(stem) {
  return CAMERA_PATTERNS.some((pattern) => pattern.test(stem.trim()));
}

export function lotPart(value) {
  return String(value).trim().replace(/[^A-Za-z0-9-]+/g, "-").replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export function lotCodeFor(lot) {
  const parts = [lot.subject, lot.classId, lot.assessment].map(lotPart);
  if (parts.some((part) => !part)) {
    return null;
  }
  return `${new Date().getFullYear()}_${parts.join("_")}`;
}

function pageSignal(stem) {
  for (const [pattern, explicit] of [[PAGE_MARKER, true], [COPY_MARKER, false], [BARE_NUMBER, false]]) {
    const match = stem.match(pattern);
    if (match) {
      const base = match[1].replace(/[\s._-]+$/, "");
      if (base) {
        return { base, explicit };
      }
    }
  }
  return null;
}

export function detectPageGroups(names) {
  const entries = names.map((name) => ({ name, stem: fileStem(name), signal: pageSignal(fileStem(name)) }));
  const byBase = new Map();
  entries.forEach((entry) => {
    if (entry.signal) {
      const key = entry.signal.base.toLowerCase();
      byBase.set(key, byBase.get(key) || []);
      byBase.get(key).push(entry);
    }
  });
  entries.forEach((entry) => {
    if (!entry.signal && byBase.has(entry.stem.toLowerCase())) {
      byBase.get(entry.stem.toLowerCase()).push(entry);
    }
  });
  const groups = [];
  byBase.forEach((members) => {
    const explicit = members.some((member) => member.signal && member.signal.explicit);
    const plausibleImplicitGroup = members.length >= 2 && members.length <= MAX_IMPLICIT_PAGE_GROUP;
    if (explicit || plausibleImplicitGroup) {
      groups.push(members.map((member) => member.name));
    }
  });
  return groups;
}
