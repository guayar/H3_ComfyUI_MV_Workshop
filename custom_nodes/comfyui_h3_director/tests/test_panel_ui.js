// Test interfejsu panelu w Chromium (Playwright). Uruchomienie: node panel/test_panel_ui.js
"use strict";
const path = require("path");
const assert = require("assert");
const { chromium } = require("playwright");

(async () => {
  const url = "file://" + path.join(__dirname, "..", "web", "h3_director_panel.html");
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(url);

  // 1. dwa ujecia, wpisane czasy w roznych formatach
  await page.click("#btnAddShot");
  await page.click("#btnAddShot");
  const starts = page.locator("#shots tr td:nth-child(2) input");
  const ends = page.locator("#shots tr td:nth-child(3) input");
  await starts.nth(0).fill("0");
  await starts.nth(0).press("Tab");
  await ends.nth(0).fill("5.17");
  await ends.nth(0).press("Tab");
  await starts.nth(1).fill("0:05.17");
  await starts.nth(1).press("Tab");
  await ends.nth(1).fill("0:15.3");
  await ends.nth(1).press("Tab");

  const frames = await page.locator("#shots tr td.frames").allInnerTexts();
  assert.deepStrictEqual(frames, ["124 kl.", "243 kl."], `klatki: ${frames}`);
  console.log("OK 1: czasy w formacie 0:05.17 i 5.17 daja 124 i 243 klatki (17n+5)");

  // 2. zly czas jest odrzucany (pole czerwone, plan bez zmian)
  await ends.nth(0).fill("1:75");
  await ends.nth(0).press("Tab");
  const cls = await ends.nth(0).getAttribute("class");
  assert.ok(cls && cls.includes("bad"), "pole z zlym czasem powinno byc oznaczone");
  console.log("OK 2: zly czas oznaczony jako bledny");
  await ends.nth(0).fill("5.17");
  await ends.nth(0).press("Tab");

  // 3. progresywne referencje obrazow: przy 2 ujeciach limit 8
  const imgInput = page.locator(".refgroup").nth(0).locator("input");
  const imgAdd = page.locator(".refgroup").nth(0).locator("button", { hasText: "Dodaj" });
  for (let i = 1; i <= 8; i++) {
    await imgInput.fill(`ref_${i}.png`);
    await imgAdd.click();
  }
  const counter = await page.locator(".refgroup").nth(0).locator(".counter").innerText();
  assert.strictEqual(counter, "8 / 8");
  assert.strictEqual(await imgAdd.isDisabled(), true, "przycisk Dodaj powinien byc wylaczony przy limicie");
  assert.strictEqual(await imgInput.isDisabled(), true, "pole nazwy powinno byc wylaczone przy limicie");
  const items = await page.locator(".refgroup").nth(0).locator(".refitem").count();
  assert.strictEqual(items, 8);
  console.log("OK 3: 8 obrazow przy 2 ujeciach, dalsze dodawanie zablokowane");

  // 4. usuniecie jednej pozycji odblokowuje dodawanie i zageszcza liste
  await page.locator(".refgroup").nth(0).locator(".refitem button").nth(0).click();
  assert.strictEqual(await page.locator(".refgroup").nth(0).locator(".counter").innerText(), "7 / 8");
  assert.strictEqual(await imgAdd.isDisabled(), false);
  const first = await page.locator(".refgroup").nth(0).locator(".refitem").nth(0).innerText();
  assert.ok(first.includes("ref_2.png"), `po usunieciu pierwsza pozycja to ${first}`);
  console.log("OK 4: usuniecie odblokowuje dodawanie, lista sie zageszcza");

  // 5. eksport: JSON zgodny z planem (klatki i limity)
  const json = JSON.parse(await page.locator("#jsonOut").innerText());
  assert.strictEqual(json.shots[0].frames, 124);
  assert.strictEqual(json.shots[1].frames, 243);
  assert.strictEqual(json.refs.images.length, 7);
  console.log("OK 5: eksport planu (JSON) zgodny z widokiem");

  // 6. przy przekroczeniu dlugosci ujecia panel pokazuje blad, a eksport jest zablokowany
  await ends.nth(1).fill("0:20");
  await ends.nth(1).press("Tab");
  const msgs = await page.locator("#msgs").innerText();
  assert.ok(/14,4/.test(msgs), "brak komunikatu o zbyt dlugim ujeciu");
  assert.strictEqual(await page.locator("#btnExport").isDisabled(), true);
  console.log("OK 6: zbyt dlugie ujecie: blad i zablokowany eksport");

  // 7. import zapisanego planu odtwarza widok
  await page.setInputFiles("#fileImport", {
    name: "plan.json", mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify({ version: 1, fps: 24, duration: 60, shots: [{ start: 0, end: 10.1, prompt: "x" }], refs: { images: ["set_plate.png"], videos: [], audio: [] } })),
  });
  await page.waitForTimeout(300);
  assert.strictEqual(await page.locator("#shots tr").count(), 1);
  assert.strictEqual(await page.locator("#shots tr td.frames").innerText(), "243 kl.");
  console.log("OK 7: import planu odtwarza ujecia i klatki");

  // 8. komunikacja z wezlem ComfyUI: rodzic (wezel) dostaje plan po zmianie i wysyla plan do panelu
  const parentHtml = `<!doctype html><meta charset="utf-8"><script>
    window.received = [];
    window.addEventListener("message", (ev) => {
      if (ev.data && ev.data.type === "h3-plan-request") {
        ev.source.postMessage({ type: "h3-plan-init", plan: JSON.stringify({ version: 1, fps: 24, duration: 60,
          shots: [{ start: 0, end: 10.1, frames: 243, prompt: "from node" }],
          refs: { images: ["set_plate.png"], videos: [], audio: [] } }) }, "*");
      }
      if (ev.data && ev.data.type === "h3-plan-update") window.received.push(ev.data.plan);
    });
    window.open(${JSON.stringify(url)}, "panel");
  </script>`;
  const fs = require("fs");
  const os = require("os");
  const parentPath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "h3p-")), "parent.html");
  fs.writeFileSync(parentPath, parentHtml);
  const parent = await browser.newPage();
  await parent.goto("file://" + parentPath);
  const popup = await parent.waitForEvent("popup");
  await popup.waitForLoadState();
  await popup.waitForFunction(() => document.querySelectorAll("#shots tr").length === 1, null, { timeout: 5000 });
  assert.strictEqual(await popup.locator("#shots tr td.frames").innerText(), "243 kl.");
  await popup.locator("#btnAddShot").click();
  await popup.waitForTimeout(200);
  const received = await parent.evaluate(() => window.received);
  assert.ok(received.length >= 1, "wezel nie dostal planu z panelu");
  const last = JSON.parse(received[received.length - 1]);
  assert.strictEqual(last.shots.length, 2);
  console.log("OK 8: panel wczytuje plan z wezla i wysyla zmiany do wezla");

  assert.deepStrictEqual(errors, [], "bledy w konsoli: " + errors.join(" | "));
  await browser.close();
  console.log("\nWszystkie testy interfejsu panelu OK.");
})().catch((e) => { console.error("FAIL:", e.message); process.exit(1); });
