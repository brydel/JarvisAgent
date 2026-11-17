import { expect, test } from "@playwright/test";

test.use({ launchOptions: {
  executablePath: process.env.JARVIS_TEST_BROWSER_EXECUTABLE || undefined,
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
} });

test("le plasma remplace les points et respecte la teinte de chaque groupe", async ({ page }) => {
  test.setTimeout(150_000);
  const erreurs: string[] = [];
  page.on("pageerror", (e) => erreurs.push(e.message));
  await page.goto("/v2/?demo=1&vue=fichiers");
  const graphe = page.locator(".mf-graphe-memoire");
  await graphe.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await expect(graphe.locator(".mf-plasma")).toHaveAttribute("data-pret", "true", { timeout: 40_000 });
  await expect(graphe.locator(".mf-plasma-source canvas")).toHaveCount(1);
  await expect(graphe.locator('[data-id="BO-demo-note"] .mf-orbe')).toHaveCSS("visibility", "hidden");
  await expect.poll(() => graphe.evaluate((zone) => {
    const toile = zone.querySelector<HTMLCanvasElement>(".mf-plasma-copie");
    const ctx = toile?.getContext("2d");
    if (!toile || !ctx || !toile.width) return false;
    const cadre = toile.getBoundingClientRect();
    const px = toile.width / cadre.width, py = toile.height / cadre.height;
    const couleur = (sommet: HTMLElement) => {
      const orbe = sommet.querySelector(".mf-orbe")?.getBoundingClientRect();
      if (!orbe) return null;
      const cx = (orbe.x + orbe.width / 2 - cadre.x) * px;
      const cy = (orbe.y + orbe.height / 2 - cadre.y) * py;
      const rayon = Math.max(9, Math.ceil(orbe.width * px));
      const x = Math.max(0, Math.floor(cx - rayon));
      const y = Math.max(0, Math.floor(cy - rayon));
      const largeur = Math.min(toile.width, Math.ceil(cx + rayon)) - x;
      const hauteur = Math.min(toile.height, Math.ceil(cy + rayon)) - y;
      if (largeur <= 0 || hauteur <= 0) return null;
      const pixels = ctx.getImageData(x, y, largeur, hauteur).data;
      const somme = [0, 0, 0];
      for (let i = 0; i < pixels.length; i += 4) {
        for (let canal = 0; canal < 3; canal++) somme[canal] = somme[canal]! + pixels[i + canal]! * pixels[i + 3]!;
      }
      return somme;
    };
    const etalon = document.createElement("canvas");
    etalon.width = etalon.height = 1;
    const contexteEtalon = etalon.getContext("2d");
    if (!contexteEtalon) return false;
    const dominantes = new Map<string, number>();
    for (const sommet of zone.querySelectorAll<HTMLElement>(".mf-sommet[data-groupe]")) {
      contexteEtalon.clearRect(0, 0, 1, 1);
      contexteEtalon.fillStyle = getComputedStyle(sommet).color;
      contexteEtalon.fillRect(0, 0, 1, 1);
      const attendue = Array.from(contexteEtalon.getImageData(0, 0, 1, 1).data).slice(0, 3);
      const mesuree = couleur(sommet);
      if (!attendue || attendue.length < 3 || !mesuree || !mesuree.some((c) => c > 0)) continue;
      const dominante = attendue.indexOf(Math.max(...attendue));
      const seconde = [...attendue].sort((a, b) => b - a)[1]!;
      if (attendue[dominante]! - seconde < 12) continue;
      if (mesuree.indexOf(Math.max(...mesuree)) !== dominante) continue;
      dominantes.set(sommet.dataset.groupe!, dominante);
    }
    return new Set(dominantes.values()).size >= 2;
  }), { timeout: 30_000 }).toBe(true);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(graphe.locator(".mf-plasma-copie")).toHaveCount(0);
  await expect(graphe.locator('[data-id="BO-demo-note"] .mf-orbe')).toHaveCSS("visibility", "visible");
  expect(erreurs).toEqual([]);
});

test("un point se déplace librement et laisse ses voisins à leur place", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/v2/?demo=1&vue=fichiers");
  const graphe = page.locator(".mf-graphe-memoire");
  await graphe.scrollIntoViewIfNeeded();
  const groupes = graphe.getByRole("button", { name: "Afficher les groupes" });
  await expect(groupes).toHaveAttribute("aria-pressed", "true");
  await groupes.click();
  await expect(groupes).toHaveAttribute("aria-pressed", "false");
  await groupes.click();
  await expect(groupes).toHaveAttribute("aria-pressed", "true");
  await expect(graphe.locator(".mf-groupes polygon").first()).toBeVisible();
  const origine = graphe.locator('[data-id="BO-demo-note"] .mf-orbe');
  const voisin = graphe.locator('[data-id="BO-demo-pdf"]');
  const position = await voisin.evaluate((el) => (el as HTMLElement).style.transform);
  const noeudOrigine = graphe.locator('[data-id="BO-demo-note"]');
  const positionOrigine = await noeudOrigine.evaluate((el) => (el as HTMLElement).style.transform);
  const centre = await origine.evaluate((el) => {
    const rect = el.getBoundingClientRect();
    return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
  });
  expect(await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest(".react-flow__node")?.getAttribute("data-id"), centre)).toBe("BO-demo-note");
  await page.mouse.move(centre.x, centre.y);
  await page.mouse.down();
  await page.mouse.move(centre.x + 70, centre.y + 30, { steps: 10 });
  await page.mouse.up();
  await expect.poll(() => noeudOrigine.evaluate((el) => (el as HTMLElement).style.transform)).not.toBe(positionOrigine);
  expect(await voisin.evaluate((el) => (el as HTMLElement).style.transform)).toBe(position);
});
