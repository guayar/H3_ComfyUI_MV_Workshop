// Testy logiki planu panelu H3 Director. Uruchomienie: node panel/test_plan_core.js
"use strict";
const assert = require("assert");
const P = require("../web/plan_core.js");

function throwsWith(fn, pattern) {
  let err = null;
  try { fn(); } catch (e) { err = e; }
  assert.ok(err, "oczekiwano bledu");
  assert.match(err.message, pattern);
}

// 1. czas: rozne formaty
assert.strictEqual(P.parseTime("12.5"), 12.5);
assert.strictEqual(P.parseTime("1:02.5"), 62.5);
assert.strictEqual(P.parseTime("0:01:02.5"), 62.5);
throwsWith(() => P.parseTime("1:75"), /sekundy >= 60/);
throwsWith(() => P.parseTime("abc"), /zly format/);
throwsWith(() => P.parseTime("-3"), /zly format|>= 0/);
console.log("OK 1: parsowanie czasu");

// 2. zaokraglenie do 17n+5
assert.strictEqual(P.snapFrames(5.17, 24), 124);
assert.strictEqual(P.snapFrames(10.125, 24), 243);
assert.strictEqual(P.snapFrames(4, 24), 90);
for (let s = 0.5; s < 14; s += 0.37) {
  const f = P.snapFrames(s, 24);
  assert.strictEqual((f - 5) % 17, 0, `klatki ${f} poza siatka 17n+5`);
}
console.log("OK 2: wszystkie dlugosci w siatce 17n+5");

// 3. walidacja ujec
let v = P.validateShots([{ start: 0, end: 10, prompt: "a" }, { start: 9, end: 20, prompt: "b" }]);
assert.ok(v.errors.some((e) => /nachodza/.test(e)));
v = P.validateShots([{ start: 0, end: 20, prompt: "a" }]);
assert.ok(v.errors.some((e) => /14,4/.test(e)));
v = P.validateShots([{ start: 0, end: 5, prompt: "" }, { start: 5, end: 10, prompt: "x" }]);
assert.ok(v.warnings.some((w) => /pusty prompt/.test(w)));
console.log("OK 3: nakladanie, zbyt dlugie ujecie i pusty prompt wykryte");

// 4. progresywne referencje obrazow: limit 8 przy wielu ujeciach, 9 przy jednym
let refs = P.emptyRefs();
for (let i = 1; i <= 8; i++) refs = P.addRef(refs, "images", `img_${i}.png`, 3);
throwsWith(() => P.addRef(refs, "images", "img_9.png", 3), /limit images: 8/);
let refs1 = P.emptyRefs();
for (let i = 1; i <= 9; i++) refs1 = P.addRef(refs1, "images", `img_${i}.png`, 1);
throwsWith(() => P.addRef(refs1, "images", "img_10.png", 1), /limit images: 9/);
console.log("OK 4: obrazy: 8 przy wielu ujeciach (1 slot na poprzednia klatke), 9 przy jednym");

// 5. wideo i audio maja wlasne limity 3
let r = P.emptyRefs();
for (let i = 1; i <= 3; i++) r = P.addRef(r, "videos", `v${i}.mp4`, 2);
throwsWith(() => P.addRef(r, "videos", "v4.mp4", 2), /limit videos: 3/);
for (let i = 1; i <= 3; i++) r = P.addRef(r, "audio", `a${i}.wav`, 2);
throwsWith(() => P.addRef(r, "audio", "a4.wav", 2), /limit audio: 3/);
console.log("OK 5: wideo i audio: limit 3 kazdy");

// 6. zla nazwa i zle rozszerzenie
throwsWith(() => P.addRef(P.emptyRefs(), "images", "../evil.png", 2), /dozwolone/);
throwsWith(() => P.addRef(P.emptyRefs(), "images", "kot.mp4", 2), /rozszerzenie/);
throwsWith(() => P.addRef(P.emptyRefs(), "images", "", 2), /dozwolone/);
console.log("OK 6: nazwy plikow i rozszerzenia sprawdzane");

// 7. usuwanie zageszcza liste (progresja bez dziur)
let q = P.addRef(P.addRef(P.addRef(P.emptyRefs(), "images", "a.png", 2), "images", "b.png", 2), "images", "c.png", 2);
q = P.removeRef(q, "images", 0);
assert.deepStrictEqual(q.images, ["b.png", "c.png"]);
console.log("OK 7: usuniecie zageszcza liste referencji");

// 8. eksport planu: klatki i walidacja przy zapisie
const plan = P.makePlan(248.76);
plan.shots = [
  { start: 0, end: 5.17, prompt: "Gardener enters the hall." },
  { start: 5.17, end: 15.3, prompt: "He turns toward the roses." },
];
plan.refs = P.addRef(P.emptyRefs(), "images", "set_plate.png", 2);
const json = P.planToJSON(plan);
assert.strictEqual(json.shots[0].frames, 124);
assert.strictEqual(json.shots[1].frames, 243);
assert.strictEqual(json.version, 1);
assert.deepStrictEqual(json.refs.images, ["set_plate.png"]);
console.log("OK 8: eksport planu z liczba klatek 17n+5");

// 9. eksport odrzuca plan z przekroczeniem limitu
const bad = P.makePlan(20);
bad.shots = [{ start: 0, end: 20, prompt: "x" }];
throwsWith(() => P.planToJSON(bad), /14,4/);
console.log("OK 9: zly plan nie jest eksportowany");

console.log("\nWszystkie testy logiki panelu OK.");
