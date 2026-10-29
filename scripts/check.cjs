// Headless check of the site: the start page (Belgrade's map), then each city's map (renders,
// buildings in the tiles, no console errors, address search, a building card,
// language switch). Works locally (python3 ../web/serve.py 8750 dist) or on a
// deployment:   node scripts/check.cjs <baseUrl> [outDir]
// Prints a JSON report, screenshots to outDir, exits 1 on any failure.
const fs = require('fs'), os = require('os'), path = require('path');
const pw = (() => { for (const t of [process.env.PLAYWRIGHT_MODULE, 'playwright', '/opt/node-tools/node_modules/playwright'].filter(Boolean)) { try { return require(t); } catch (e) {} } throw new Error('playwright not found'); })();
const BASE = (process.argv[2] || 'http://localhost:8750').replace(/\/$/, '');
const OUT = process.argv[3] || fs.mkdtempSync(path.join(os.tmpdir(), 'bg-check-'));
const CITIES = {
  zurich: { query: 'Bahnhofstrasse 1', lang: 'en', at: { center: [8.5285, 47.3745], zoom: 17 } },
  belgrade: { query: 'Resavska', lang: 'en', at: { center: [20.4605, 44.8125], zoom: 17 }, air: true },
};
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const report = { base: BASE, out: OUT, failures: [], cities: {} };
  const fail = m => report.failures.push(m);
  const browser = await pw.chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const ownHost = new URL(BASE).host;
  const watch = (page, tag) => {
    page.on('console', m => { if (m.type() === 'error' && !/^Failed to load resource/.test(m.text())) fail(`${tag}: console: ${m.text()}`); });
    page.on('pageerror', e => fail(`${tag}: pageerror: ${e}`));
    page.on('response', r => { if (r.status() >= 400 && new URL(r.url()).host === ownHost) fail(`${tag}: ${r.status()} ${r.url()}`); });
  };
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  // the start page is Belgrade's map (C-23): it loads, draws buildings, and its menu links the reference
  let page = await ctx.newPage(); watch(page, 'start');
  await page.goto(`${BASE}/`, { waitUntil: 'load' });
  try {
    await page.waitForFunction(() => typeof map !== "undefined" && map.loaded && map.loaded(), null, { timeout: 90000 });
  } catch (e) { fail('start: map never loaded'); }
  report.start = { city: await page.evaluate(() => typeof CITY !== "undefined" ? CITY.id : null), title: await page.title() };
  if (report.start.city !== 'belgrade') fail(`start: the start page shows ${report.start.city}, not belgrade`);
  await page.evaluate(() => map.jumpTo({ center: [20.4605, 44.8125], zoom: 17 }));
  await page.waitForFunction(() => map.loaded() && map.areTilesLoaded(), null, { timeout: 90000 }).catch(() => {});
  await page.waitForTimeout(1000);
  if (!(await page.evaluate(() => map.queryRenderedFeatures().some(f => f.sourceLayer === 'buildings')))) fail('start: no buildings');
  await page.click('.bc-menu-btn, [aria-label="Menu"], [aria-label="Meni"], [aria-label="Menü"]').catch(() => {});
  await page.waitForTimeout(500);
  const links = await page.$$eval('a', as => as.map(a => a.getAttribute('href')));
  if (!links.includes('/zurich/')) fail('start: no menu link to the reference (/zurich/)');
  await page.screenshot({ path: path.join(OUT, 'start.png') });
  await page.close();
  for (const [c, cfg] of Object.entries(CITIES)) {
    const r = report.cities[c] = {};
    page = await ctx.newPage(); watch(page, c);
    await page.goto(`${BASE}/${c}/`, { waitUntil: 'load' });
    try {
      await page.waitForFunction(() => typeof map !== "undefined" && map.loaded && map.loaded() && map.areTilesLoaded(), null, { timeout: 90000 });
    } catch (e) { fail(`${c}: map never loaded`); }
    await page.screenshot({ path: path.join(OUT, `${c}_start.png`) });
    await page.evaluate(at => map.jumpTo(at), cfg.at);
    await page.waitForFunction(() => typeof map !== "undefined" && map.loaded && map.loaded() && map.areTilesLoaded(), null, { timeout: 90000 }).catch(() => {});
    await page.waitForTimeout(1500);
    r.buildings = await page.evaluate(() => map.queryRenderedFeatures().filter(f => f.sourceLayer === 'buildings').length);
    if (!r.buildings) fail(`${c}: no buildings rendered at z17`);
    await page.screenshot({ path: path.join(OUT, `${c}_z17.png`) });
    // a building card: click the canvas centre's building
    const box = await page.locator('canvas').first().boundingBox();
    const hit = await page.evaluate(() => {
      const fs = map.queryRenderedFeatures().filter(f => f.sourceLayer === 'buildings' && f.properties.address);
      if (!fs.length) return null;
      const g = fs[0].geometry.coordinates.flat(3); const pts = []; for (let i = 0; i + 1 < g.length; i += 2) pts.push([g[i], g[i + 1]]);
      const lng = pts.reduce((s, p) => s + p[0], 0) / pts.length, lat = pts.reduce((s, p) => s + p[1], 0) / pts.length;
      const p = map.project([lng, lat]); return { x: p.x, y: p.y };
    });
    if (hit) {
      await page.mouse.click(box.x + hit.x, box.y + hit.y);
      await page.waitForTimeout(1200);
      r.card = await page.evaluate(() => { const el = document.querySelector('.maplibregl-popup-content'); return el ? el.innerText.slice(0, 400) : null; });
      if (!r.card) fail(`${c}: no card on click`);
      r.naChips = await page.evaluate(() => document.querySelectorAll('.maplibregl-popup-content .hc-fig-na, .maplibregl-popup-content [class*="na"]').length);
      await page.screenshot({ path: path.join(OUT, `${c}_card.png`) });
      await page.keyboard.press('Escape');
    } else fail(`${c}: no addressed building at the check point`);
    // address search
    const input = page.locator('input[type="search"], .bc-search input').first();
    if (await input.count()) {
      await input.fill(cfg.query);
      await page.waitForTimeout(2500);
      r.searchHits = await page.evaluate(() => [...document.querySelectorAll('[role="option"]')].slice(0, 3).map(e => e.innerText));
      if (!r.searchHits.length) fail(`${c}: search "${cfg.query}" found nothing`);
      await page.screenshot({ path: path.join(OUT, `${c}_search.png`) });
    } else fail(`${c}: no search field`);
    // the commute lens and a stop card (both cities have stops and the commute)
    await page.goto(`${BASE}/${c}/?color=commute`, { waitUntil: 'load' });
    await page.waitForFunction(() => typeof map !== "undefined" && map.loaded && map.loaded(), null, { timeout: 90000 }).catch(() => fail(`${c}: commute lens never loaded`));
    await page.evaluate(at => map.jumpTo({ ...at, zoom: 16 }), cfg.at);
    await page.evaluate(() => controls.showPlace('s'));
    await page.waitForFunction(() => map.loaded() && map.areTilesLoaded(), null, { timeout: 90000 }).catch(() => {});
    await page.waitForTimeout(1500);
    r.commuteShaded = await page.evaluate(() => map.queryRenderedFeatures().filter(f => f.sourceLayer === 'buildings' && f.properties.commute_hb_min != null).length);
    if (!r.commuteShaded) fail(`${c}: no building with a commute value`);
    await page.screenshot({ path: path.join(OUT, `${c}_commute.png`) });
    const stop = await page.evaluate(() => { const f = map.queryRenderedFeatures().find(f => f.sourceLayer === 'stops'); if (!f) return null; const p = map.project(f.geometry.coordinates); return { x: p.x, y: p.y }; });
    if (stop) {
      const b = await page.locator('canvas').first().boundingBox();
      await page.mouse.click(b.x + stop.x, b.y + stop.y);
      await page.waitForTimeout(2500);
      r.stopCard = await page.evaluate(() => { const el = document.querySelector('.maplibregl-popup-content .sc-card'); return el ? el.innerText.slice(0, 200) : null; });
      if (!r.stopCard) fail(`${c}: no stop card on click`);
      await page.screenshot({ path: path.join(OUT, `${c}_stop.png`) });
    } else fail(`${c}: no stop rendered`);
    // air-quality stations (Belgrade only; a greyed layer in Zürich)
    if (cfg.air) {
      await page.goto(`${BASE}/${c}/?places=q`, { waitUntil: 'load' });
      await page.waitForFunction(() => typeof map !== "undefined" && map.loaded && map.loaded(), null, { timeout: 90000 }).catch(() => {});
      await page.evaluate(() => map.jumpTo({ center: [20.462, 44.805], zoom: 13 }));
      await page.waitForFunction(() => map.loaded() && map.areTilesLoaded(), null, { timeout: 90000 }).catch(() => {});
      await page.waitForTimeout(1500);
      r.airStations = await page.evaluate(() => map.queryRenderedFeatures({ layers: ['place-air'] }).length);
      if (!r.airStations) fail(`${c}: no air-quality station rendered`);
    }
    // language
    await page.goto(`${BASE}/${c}/?lang=${cfg.lang}`, { waitUntil: 'load' });
    await page.waitForTimeout(3000);
    r.htmlLang = await page.evaluate(() => document.documentElement.lang);
    r.title = await page.title();
    await page.screenshot({ path: path.join(OUT, `${c}_${cfg.lang}.png`) });
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(report, null, 2));
  process.exit(report.failures.length ? 1 : 0);
})();
