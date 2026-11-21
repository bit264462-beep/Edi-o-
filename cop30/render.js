// Renderiza cop30.html quadro a quadro (30 fps, 15 s = 450 quadros) para PNGs.
const { chromium } = require('playwright');
const path = require('path');
const FR = process.argv[2];
const N = 450, FPS = 30;
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto('file:///home/claude/cop30/cop30.html');
  await page.evaluate(() => document.fonts.ready);
  for (let i = 0; i < N; i++) {
    await page.evaluate(t => window.render(t), i / FPS);
    await page.screenshot({ path: path.join(FR, `f_${String(i).padStart(4, '0')}.png`) });
  }
  await browser.close();
  console.log('frames:', N);
})();
