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
const input = page.locator(".word-input input");
const clean = (s) => s.replace(/\s+/g, " ").trim();

async function submitWord(word) {
  await input.fill(word);
  await input.press("Escape"); // close autocomplete so the click lands
  await page.click(".entry-row .btn.primary");
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

// Autocomplete only completes prefixes of 3+ letters.
await input.fill("ba");
check((await page.locator(".suggestions li").count()) === 0, "no suggestions under 3 letters");
await input.fill("ban");
const sugg = await page.locator(".suggestions li").allInnerTexts();
check(sugg.length > 0 && sugg.every((s) => s.startsWith("ban")), "3-letter prefix suggestions", sugg.join(", "));
await input.fill("");

// A real word that doesn't connect costs a strike.
for (const word of ["banana", "volcano", "pencil", "elephant"]) {
  await submitWord(word);
  if ((await page.locator(".strike.used").count()) > 0) break;
}
check((await page.locator(".strike.used").count()) === 1, "strike shown", await toast());

// Hint appears as a ghost tile and is counted.
await page.click("text=Hint");
await page.waitForTimeout(300);
const hintTile = page.locator(".tile.hint");
check((await hintTile.count()) === 1, "hint tile shown", await hintTile.innerText().catch(() => ""));
await shot("2-strike-and-hint");
await hintTile.click();
await page.waitForTimeout(400);
check((await page.locator(".actions .btn.secondary").innerText()).includes("1 used"), "hint counted");

// Refresh mid-game resumes the same chain.
const before = await page.locator(".board").innerText();
await page.reload();
await page.waitForSelector(".tile.start");
await page.waitForTimeout(400);
check((await page.locator(".board").innerText()) === before, "refresh resumes the game");

// Finish by following hints (typing the target when one away).
for (let i = 0; i < 8 && !(await page.locator(".result-card").count()); i++) {
  await page.click("text=Hint");
  await page.waitForTimeout(250);
  const tile = page.locator(".tile.hint");
  if (await tile.count()) {
    await tile.click();
    await page.waitForTimeout(400);
  } else {
    await submitWord(await page.locator(".tile.target").innerText());
  }
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
await page.click("text=Hint");
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
