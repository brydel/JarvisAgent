import { chromium } from "@playwright/test";

const charge = process.argv[2] ?? "100";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1672, height: 941 } });
p.on("pageerror", (e) => console.log("pageerror", e.message.slice(0, 200)));
const t0 = Date.now();
await p.goto(`http://localhost:7720/v2/?demo=1&charge=${charge}`);
await p.locator(".react-flow__node").first().waitFor();
console.log("premier nœud", Date.now() - t0, "ms");
const sonde = async (nom) => {
  const t = Date.now();
  const r = await Promise.race([p.evaluate(() => document.querySelectorAll(".react-flow__node").length), new Promise((res) => setTimeout(() => res("BLOQUÉ"), 8000))]);
  console.log(nom, "→ nœuds", r, "en", Date.now() - t, "ms");
};
await sonde("après chargement");
await p.getByRole("button", { name: "Ajuster à la vue" }).click({ timeout: 8000 }).catch((e) => console.log("clic ajuster:", e.message.slice(0, 80)));
await sonde("après ajuster");
await p.waitForTimeout(2000);
await sonde("2 s plus tard");
const box = await p.locator(".react-flow__pane").boundingBox({ timeout: 8000 }).catch((e) => "échec " + e.message.slice(0, 60));
console.log("pane", box);
const t = Date.now();
const longues = await p.evaluate(() => new Promise((res) => {
  let n = 0, t0 = performance.now(), fin = performance.now() + 2000;
  const f = (x) => { if (x - t0 > 50) n++; t0 = x; if (x < fin) requestAnimationFrame(f); else res(n); };
  requestAnimationFrame(f);
}));
console.log("images > 50 ms au repos sur 2 s :", longues, "(", Date.now() - t, "ms )");
await b.close();
