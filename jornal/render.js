// Renderiza um modo do estúdio (intro, map, lower, event) quadro a quadro.
// Uso: node render.js studio.html cfg.json <saida_dir> <fps> <duracao_s> <transparente 0|1>
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const [, , html, cfgFile, outDir, fpsArg, durArg, transpArg] = process.argv;
const cfg = JSON.parse(fs.readFileSync(cfgFile, 'utf8'));
const fps = Number(fpsArg), dur = Number(durArg), transparent = transpArg === '1';
const N = Math.round(dur * fps);

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.resolve(html));
  await page.evaluate(c => document.fonts.ready.then(() => window.setup(c.mode, c)), cfg);
  for (let i = 0; i < N; i++) {
    await page.evaluate(t => window.render(t), i / fps);
    await page.screenshot({
      path: path.join(outDir, `f_${String(i).padStart(4, '0')}.png`),
      omitBackground: transparent,
    });
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
