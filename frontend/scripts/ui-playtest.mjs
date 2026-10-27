// Drive the built UI in the local Google Chrome and screenshot each stage.
//
//   node scripts/ui-playtest.mjs <base_url> <screenshot_dir>
//
// Starts from a fresh browser profile (first-visit help modal, today's daily).
// Exits non-zero if any check fails or the page logs an error.
import { mkdirSync } from "node:fs";
import { chromium } from "playwright-core";

const [base = "http://localhost:8000", out = "playtest-output"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });

const failures = [];
function check(ok, label, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? `  (${detail})` : ""}`);
  if (!ok) failures.push(label);
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await ctx.grantPermissions(["clipboard-read", "clipboard-write"]);
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

const shot = (name) => page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
const toast = () => page.locator(".toast").textContent().catch(() => null);
const clean = (s) => s.replace(/\s+/g, " ").trim();
const played = () => page.locator(".tile.played").count();
const hintButton = page.locator(".actions button", { hasText: "Hint" });

async function play(locator) {
  await locator.click();
  await page.waitForTimeout(400);
}

// First visit: help modal, then today's daily.
await page.goto(base);
await page.waitForSelector(".modal");
await shot("1-first-visit-help");
await page.click(".modal-close");
await page.waitForSelector(".tile.start");
const meter = clean(await page.locator(".meter").innerText());
check(/DAILY #\d+/i.test(meter) && /PAR \d/i.test(meter), "opens on the daily with par shown", meter);

// The board: tiles plus the target, and Back disabled at the start.
const picks = page.locator(".tile-grid .pick");
const tiles = await picks.allInnerTexts();
check(tiles.length >= 5 && (await page.locator(".pick.target").count()) === 1, "tile grid shown", tiles.join(", "));
check(await page.locator(".actions button", { hasText: "Back" }).isDisabled(), "back disabled at the start");

// Play tiles until one costs a strike, taking back any that connect.
let tookBack = false;
for (let i = 0; i < tiles.length - 1 && !(await page.locator(".strike.used").count()); i++) {
  const pick = picks.nth(i);
  if (await pick.isDisabled()) continue;
  await play(pick);
  if ((await played()) > 0) {
    await page.click(".actions button:has-text('Back')");
    await page.waitForTimeout(300);
    tookBack = true;
    check((await played()) === 0, "back removes the last word");
  }
}
check((await page.locator(".strike.used").count()) === 1, "strike shown", await toast());
check((await page.locator(".pick.struck").count()) === 1, "struck tile marked");
if (tookBack) {
  check(/7 moves left/.test(await page.locator(".fine-print").innerText()), "taken-back move still counts",
    clean(await page.locator(".fine-print").innerText()));
}

// Hint appears as a ghost tile and is counted.
await hintButton.click();
await page.waitForTimeout(300);
const hintTile = page.locator(".tile.hint");
check((await hintTile.count()) === 1 && (await page.locator(".pick.hinted").count()) === 1,
  "hint shown in the chain and on the board", await hintTile.innerText().catch(() => ""));
await shot("2-strike-and-hint");
await hintTile.click();
await page.waitForTimeout(400);
check((await hintButton.innerText()).includes("1 used"), "hint counted");

// Refresh mid-game resumes the same chain.
const before = await page.locator(".board").innerText();
await page.reload();
await page.waitForSelector(".tile.start");
await page.waitForTimeout(400);
check((await page.locator(".board").innerText()) === before, "refresh resumes the game");

// Finish by following hints (tapping the target when one away).
for (let i = 0; i < 8 && !(await page.locator(".result-card").count()); i++) {
  await hintButton.click();
  await page.waitForTimeout(250);
  const tile = page.locator(".tile.hint");
  await play((await tile.count()) ? tile : page.locator(".pick.target"));
}
await page.waitForSelector(".result-card");
await page.waitForTimeout(1400); // result card fades in
const result = clean(await page.locator(".result-card").innerText());
check(result.startsWith("Connected!"), "hinted win is not a ⛳ par", result);
await shot("3-result");

await page.click("text=Share");
await page.waitForTimeout(300);
const shared = await page.evaluate(() => navigator.clipboard.readText());
check(/^Degrees #\d+/.test(shared) && !shared.includes("⛳"), "share text copied", shared.split("\n").join(" | "));

await page.reload();
await page.waitForSelector(".result-card");
check(true, "finished daily stays finished after refresh");

// Practice: confirm before abandoning one in progress.
await page.click("text=Practice puzzle");
await page.waitForSelector(".link-btn");
await hintButton.click();
await page.waitForTimeout(300);
await page.click("button[aria-label='New practice puzzle']");
await page.waitForTimeout(300);
check((await page.locator(".modal").count()) > 0, "confirm before abandoning practice");
await shot("4-practice-confirm");
await page.click("text=Keep playing");

await page.setViewportSize({ width: 1280, height: 900 });
await shot("5-desktop");

check(errors.length === 0, "no console errors", errors.join(" | "));
await browser.close();

console.log(failures.length ? `\n${failures.length} FAILED: ${failures.join(", ")}` : "\nALL PASSED");
console.log(`screenshots: ${out}`);
process.exit(failures.length ? 1 : 0);
