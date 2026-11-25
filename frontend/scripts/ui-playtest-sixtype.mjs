// Drive the six-type UI in the local Google Chrome and screenshot each stage.
//
//   node scripts/ui-playtest-sixtype.mjs <base_url> <screenshot_dir> <board.json>
//
// board.json (written by scripts/playtest.sh) is today's six-type daily:
// { start, target, route, route_types, tiles, unlinked } where `unlinked`
// is a tile that doesn't link to the start. Exits non-zero on any failure.
import { mkdirSync, readFileSync } from "node:fs";
import { chromium } from "playwright-core";

const [base, out, boardPath] = process.argv.slice(2);
const board = JSON.parse(readFileSync(boardPath, "utf8"));
mkdirSync(out, { recursive: true });

const failures = [];
function check(ok, label, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? `  (${detail})` : ""}`);
  if (!ok) failures.push(label);
}

const browser = await chromium.launch({ channel: "chrome", headless: true });

async function run(name, ctxOptions, body) {
  const ctx = await browser.newContext({ deviceScaleFactor: 2, ...ctxOptions });
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await body(page);
  check(errors.length === 0, `${name}: no console errors`, errors.join(" | "));
  await ctx.close();
}

const shot = (page, name) => page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
const toast = (page) => page.locator(".toast").textContent().catch(() => "");
const clean = (s) => (s ?? "").replace(/\s+/g, " ").trim();
const tile = (page, w) => page.locator(".st-tile", { hasText: new RegExp(`^${w}$`, "i") });
const spentKeys = (page) => page.locator(".st-key.spent").count();
const filled = (page) => page.locator(".st-cell.word").count();

/** Play `word`; if the type picker opens, spend `type`. */
async function play(page, word, type) {
  const target = word === board.target ? page.locator(".st-cell.end.live") : tile(page, word);
  await target.click();
  await page.waitForTimeout(350);
  if (await page.locator(".st-choice").count()) {
    const names = await page.locator(".st-choice b").allInnerTexts();
    await page.locator(".st-choice").nth(names.findIndex((n) => n.toLowerCase() === TYPE_NAMES[type])).click();
    await page.waitForTimeout(350);
    return true;
  }
  return false;
}
const TYPE_NAMES = {
  kind: "kind of", family: "same family", part: "part of / made of",
  feature: "share a feature", use: "used for / makes", found: "found with",
};

await run("phone", { viewport: { width: 390, height: 844 } }, async (page) => {
  await page.goto(base);
  await page.waitForSelector(".modal");
  const help = clean(await page.locator(".modal").innerText());
  check(/six links/i.test(help) && /each type can be spent only once/i.test(help), "help explains the six-type rules");
  await shot(page, "6-1-help");
  await page.click(".modal-close");
  await page.waitForSelector(".st-chain");

  const meter = clean(await page.locator(".meter").innerText());
  check(/DAILY #\d+/i.test(meter) && /6 LINKS/i.test(meter), "opens on the six-type daily", meter);
  check((await page.locator(".st-key").count()) === 6 && (await spentKeys(page)) === 0, "six unspent type keys");
  check((await page.locator(".st-tile").count()) === 10, "ten tiles");
  check(await page.locator(".st-pill", { hasText: "Back" }).isDisabled(), "back disabled at the start");

  // A tile that doesn't link: a mistake.
  await tile(page, board.unlinked).click();
  await page.waitForTimeout(350);
  check((await page.locator(".st-mistakes i.gone").count()) === 1, "unlinked tile is a mistake", await toast(page));
  check((await page.locator(".st-tile.shake").count()) === 1, "mistaken tile shakes");

  // First route link: fills a cell, spends a key, explains the link.
  await play(page, board.route[1], board.route_types[0]);
  check((await filled(page)) === 1 && (await spentKeys(page)) === 1, "a link fills the chain and spends a key");
  const last = clean(await page.locator(".st-last").innerText());
  check(last.toLowerCase().includes(TYPE_NAMES[board.route_types[0]]), "the link is explained", last);

  // Tapping the word in the chain takes it back and refunds the type.
  await page.locator(".st-cell.word").first().click();
  await page.waitForTimeout(400);
  check((await filled(page)) === 0 && (await spentKeys(page)) === 0, "tapping a chain word takes it back, refunding the type");

  // A hint names a type and outlines its key.
  await page.locator(".st-pill", { hasText: "Hint" }).click();
  await page.waitForTimeout(350);
  const hinted = clean(await page.locator(".st-key.hint").innerText().catch(() => ""));
  check(hinted.toLowerCase() === TYPE_NAMES[board.route_types[0]], "hint outlines the next type's key", `${hinted} / ${await toast(page)}`);
  await shot(page, "6-2-mistake-and-hint");

  // Play the route; record whether the type picker came up.
  let picked = false;
  for (let i = 1; i < board.route.length; i++) {
    if (i === 4) await shot(page, "6-3-midway");
    picked = (await play(page, board.route[i], board.route_types[i - 1])) || picked;
  }
  check(picked, "type picker offered when a link fits two unspent types");
  await page.waitForSelector(".st-result");
  const result = clean(await page.locator(".st-result").innerText());
  check(/Connected!/.test(result) && (await page.locator(".st-steps li").count()) === 6, "win shows the six steps", result.slice(0, 80));
  check((await page.locator(".st-cell.end.reached").count()) === 1, "target marked reached");
  await page.waitForTimeout(1500);   // the result card fades in
  await shot(page, "6-4-result");

  await page.locator(".st-result .btn", { hasText: "Share" }).click();
  await page.waitForTimeout(300);
  const shared = await page.evaluate(() => navigator.clipboard.readText()).catch(() => "");
  check(/Degrees #\d+ {2}6\/6\n/.test(shared) && shared.includes("↩️") && shared.includes("💡"), "share text", JSON.stringify(shared));

  await page.reload();
  await page.waitForSelector(".st-result");
  check(true, "finished daily stays finished after refresh");
});

// Desktop and dark mode, mid-game: the first two route links played.
for (const [name, opts] of [
  ["desktop", { viewport: { width: 1280, height: 900 } }],
  ["dark", { viewport: { width: 390, height: 844 }, colorScheme: "dark" }],
]) {
  await run(name, opts, async (page) => {
    await page.goto(base);
    await page.waitForSelector(".modal");
    await page.click(".modal-close");
    await page.waitForSelector(".st-chain");
    await play(page, board.route[1], board.route_types[0]);
    await play(page, board.route[2], board.route_types[1]);
    check((await spentKeys(page)) === 2, `${name}: two links played`);
    await shot(page, `6-5-${name}`);
  });
}

await browser.close();
console.log(failures.length ? `\n${failures.length} FAILED` : "\nALL PASSED");
process.exit(failures.length ? 1 : 0);
