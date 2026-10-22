// Inspection DOM ponctuelle : node scripts/inspecter.mjs <url> "<expression JS évaluée dans la page>"
import { chromium } from "@playwright/test";

const [url, expr] = process.argv.slice(2);
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1672, height: 941 } });
await p.goto(url, { waitUntil: "networkidle" });
await p.waitForTimeout(600);
console.log(JSON.stringify(await p.evaluate(expr), null, 1));
await b.close();
