/*
 * H3 Director panel: czysta logika planu (bez DOM). Dziala w przegladarce i w Node.
 *
 * Zrodla limitow [CODE nodes_minimax_h3.py]: 9 obrazow, 3 wideo, 3 audio na wezel Ref2VA.
 * Obraz poprzedniej klatki zajmuje jeden slot w ujeciach 2 i kolejnych, wiec limit obrazow
 * od uzytkownika to 8 (gdy jest wiecej niz jedno ujecie) albo 9 (gdy jedno).
 * Liczba klatek: 17n+5 przy 24 fps [CODE / szablon].
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.H3Plan = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const FPS = 24;
  const REF_LIMITS = { images: 9, videos: 3, audio: 3 };
  const EXT = {
    images: [".png", ".jpg", ".jpeg", ".webp"],
    videos: [".mp4", ".webm", ".mov", ".mkv"],
    audio: [".wav", ".mp3", ".flac", ".ogg"],
  };
  const SAFE_NAME = /^[A-Za-z0-9_\-. ]+$/;

  function parseTime(text) {
    if (typeof text === "number") {
      if (!isFinite(text) || text < 0) throw new Error("czas musi byc liczba >= 0");
      return text;
    }
    const s = String(text).trim();
    if (!s) throw new Error("pusty czas");
    const parts = s.split(":");
    if (parts.length > 3) throw new Error(`zly format czasu: ${s}`);
    const nums = parts.map((p) => p.trim());
    if (!nums.every((p) => /^\d+(\.\d+)?$/.test(p))) throw new Error(`zly format czasu: ${s}`);
    const values = nums.map(parseFloat);
    for (let i = 0; i < values.length - 1; i++) {
      if (!Number.isInteger(values[i])) throw new Error(`zly format czasu: ${s}`);
    }
    if (values.length > 1) {
      if (values[values.length - 1] >= 60) throw new Error(`sekundy >= 60 w: ${s}`);
      if (values.length === 3 && values[1] >= 60) throw new Error(`minuty >= 60 w: ${s}`);
    }
    let total = 0;
    for (const v of values) total = total * 60 + v;
    return total;
  }

  function formatTime(sec) {
    const neg = sec < 0;
    sec = Math.abs(sec);
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec - h * 3600 - m * 60;
    const ss = s.toFixed(2).padStart(5, "0");
    const body = h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
    return (neg ? "-" : "") + body;
  }

  /** Najblizsza liczba klatek w siatce 17n+5 (min 5). */
  function snapFrames(seconds, fps) {
    const raw = seconds * (fps || FPS);
    const n = Math.max(0, Math.round((raw - 5) / 17));
    return 17 * n + 5;
  }

  function shotFrames(shot) {
    return snapFrames(shot.end - shot.start, FPS);
  }

  function validateShots(shots) {
    const errors = [];
    const warnings = [];
    const sorted = shots.slice().sort((a, b) => a.start - b.start);
    sorted.forEach((s, i) => {
      if (!(s.end > s.start)) errors.push(`ujecie ${i + 1}: koniec musi byc po poczatku`);
      if (!s.prompt || !s.prompt.trim()) warnings.push(`ujecie ${i + 1}: pusty prompt`);
      if (i > 0 && s.start < sorted[i - 1].end - 1e-9) errors.push(`ujecia ${i} i ${i + 1} nachodza sie`);
      if (i > 0 && s.start > sorted[i - 1].end + 1e-9) warnings.push(`przerwa miedzy ujeciami ${i} i ${i + 1}`);
      const dur = s.end - s.start;
      if (dur > 0 && dur < 2) warnings.push(`ujecie ${i + 1} krotsze niz 2 s`);
      if (dur > 14.4) errors.push(`ujecie ${i + 1} dluzsze niz 14,4 s (limit jednej generacji)`);
    });
    return { errors, warnings };
  }

  function imageLimit(shotCount) {
    return shotCount > 1 ? REF_LIMITS.images - 1 : REF_LIMITS.images;
  }

  function emptyRefs() {
    return { images: [], videos: [], audio: [] };
  }

  function refCounts(refs, shotCount) {
    return {
      images: { used: refs.images.length, limit: imageLimit(shotCount || 1) },
      videos: { used: refs.videos.length, limit: REF_LIMITS.videos },
      audio: { used: refs.audio.length, limit: REF_LIMITS.audio },
    };
  }

  /** Dodaje referencje na pierwszy wolny slot (progresywnie). Rzuca blad przy limicie lub zlej nazwie. */
  function addRef(refs, kind, name, shotCount) {
    if (!EXT[kind]) throw new Error(`nieznany rodzaj referencji: ${kind}`);
    const clean = String(name).trim();
    if (!clean || !SAFE_NAME.test(clean)) throw new Error(`nazwa pliku: dozwolone litery, cyfry, _ - . i spacje`);
    const lower = clean.toLowerCase();
    if (!EXT[kind].some((e) => lower.endsWith(e))) throw new Error(`zle rozszerzenie dla ${kind}: ${EXT[kind].join(" ")}`);
    const counts = refCounts(refs, shotCount);
    if (counts[kind].used >= counts[kind].limit) {
      throw new Error(`limit ${kind}: ${counts[kind].limit} (model nie przyjmie wiecej)`);
    }
    const next = { images: refs.images.slice(), videos: refs.videos.slice(), audio: refs.audio.slice() };
    next[kind].push(clean);
    return next;
  }

  /** Usuwa referencje i zageszcza liste (zachowuje progresje bez dziur). */
  function removeRef(refs, kind, index) {
    const next = { images: refs.images.slice(), videos: refs.videos.slice(), audio: refs.audio.slice() };
    if (index < 0 || index >= next[kind].length) throw new Error("zly indeks referencji");
    next[kind].splice(index, 1);
    return next;
  }

  /** Aktywne referencje to pierwsze `used` slotow; reszta jest ignorowana. */
  function activeRefs(refs) {
    return { images: refs.images.slice(), videos: refs.videos.slice(), audio: refs.audio.slice() };
  }

  function validateRefs(refs, shotCount) {
    const errors = [];
    const c = refCounts(refs, shotCount);
    for (const kind of Object.keys(c)) {
      if (c[kind].used > c[kind].limit) errors.push(`za duzo referencji ${kind}: ${c[kind].used} > ${c[kind].limit}`);
    }
    if (refs.audio.length > 0 && refs.images.length === 0 && refs.videos.length === 0) {
      errors.push("audio wymaga co najmniej jednej referencji obrazu lub wideo");
    }
    return errors;
  }

  function makePlan(duration) {
    return { version: 1, fps: FPS, duration: duration, shots: [], refs: emptyRefs() };
  }

  /** Eksport do pliku, ktory czyta build_ui_chain.py --plan. */
  function planToJSON(plan) {
    const shots = plan.shots
      .slice()
      .sort((a, b) => a.start - b.start)
      .map((s) => ({
        start: round3(s.start),
        end: round3(s.end),
        frames: shotFrames(s),
        prompt: s.prompt || "",
      }));
    const errors = validateShots(plan.shots).errors.concat(validateRefs(plan.refs, shots.length));
    if (errors.length) throw new Error(errors.join("; "));
    return {
      version: 1,
      fps: FPS,
      duration: round3(plan.duration),
      shots,
      refs: { images: plan.refs.images.slice(), videos: plan.refs.videos.slice(), audio: plan.refs.audio.slice() },
    };
  }

  function round3(x) {
    return Math.round(x * 1000) / 1000;
  }

  return {
    FPS, REF_LIMITS, EXT,
    parseTime, formatTime, snapFrames, shotFrames,
    validateShots, imageLimit, emptyRefs, refCounts, addRef, removeRef, activeRefs, validateRefs,
    makePlan, planToJSON,
  };
});
