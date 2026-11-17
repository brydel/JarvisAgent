import { expect, test } from "@playwright/test";
import { ouvrir, regler } from "./outils";

test("la carte des fichiers ouvre un PDF et permet de suivre ses relations", async ({ page }) => {
  const erreurs: string[] = [];
  page.on("pageerror", (e) => erreurs.push(e.message));
  await page.goto("/v2/?demo=1&vue=fichiers");
  await expect(page.getByRole("heading", { name: "Fichiers", exact: true })).toBeVisible();
  await expect(page.locator(".react-flow__edge").first()).toBeVisible();
  await expect(page.locator(".react-flow__minimap-node").first()).toBeVisible();
  const pdf = page.locator('.react-flow__node[data-id="BO-demo-pdf"]');
  await pdf.scrollIntoViewIfNeeded();
  const orbe = await pdf.locator(".mf-orbe").boundingBox();
  expect(orbe).not.toBeNull();
  await page.mouse.click(orbe!.x + orbe!.width / 2, orbe!.y + orbe!.height / 2);
  const inspecteur = page.getByRole("complementary", { name: "Inspecteur du fichier" });
  await expect(inspecteur.getByRole("heading", { name: "Plan produit v1.0.pdf" })).toBeVisible();
  await expect(inspecteur.getByRole("status").filter({ hasText: /Page 1 \/ \d/ })).toBeVisible();
  await inspecteur.getByRole("button", { name: "Ouvrir le grand aperçu" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await inspecteur.getByRole("button", { name: "Isoler le voisinage" }).click();
  await expect(page.getByRole("button", { name: "Quitter le voisinage" })).toBeVisible();
  await page.getByRole("button", { name: "Par niveaux" }).click();
  await expect(page.locator('.react-flow__node[data-id="BO-demo-pdf"]')).toBeVisible();
  await page.getByRole("button", { name: "Liste", exact: true }).click();
  await expect(page.locator(".mf-ligne")).toHaveCount(9);
  await page.locator(".mf-ligne", { hasText: "Présentation produit.mp4" }).click();
  await expect(inspecteur.locator("video[controls]")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(erreurs).toEqual([]);
});

test("importer, relier et citer le passage d’un fichier réellement indexé", async ({ page }) => {
  await ouvrir(page);
  const destination = await page.request.post("/api/v2/objets", { headers: { "X-Jarvis-Studio": "1" },
    data: { type: "note", contenu: "Plan proposé", meta: { titre: "Contexte du projet" }, analyser: false } });
  expect(destination.ok()).toBe(true);
  const cible = (await destination.json()).objet_id;
  await page.goto("/v2/?vue=fichiers");
  await page.locator('input[type="file"]').setInputFiles({
    name: "cahier.md", mimeType: "text/markdown", buffer: Buffer.from("# Cadrage\nLa palette cobalt sera utilisée dans l’interface."),
  });
  const inspecteur = page.getByRole("complementary", { name: "Inspecteur du fichier" });
  await expect(inspecteur.getByRole("heading", { name: "cahier.md" })).toBeVisible();
  await inspecteur.getByRole("button", { name: "Relier", exact: true }).click();
  const lien = page.getByRole("dialog", { name: "Relier un fichier" });
  await lien.getByRole("combobox", { name: /Carte cible/ }).selectOption(cible);
  await lien.getByRole("combobox", { name: /Relation/ }).selectOption("alimente");
  await lien.getByRole("button", { name: "Enregistrer la relation" }).click();
  await expect(inspecteur.getByRole("button", { name: /Contexte du projet.*Alimente/ })).toBeVisible();
  await inspecteur.getByRole("button", { name: "Indexer le fichier" }).click();
  await expect(inspecteur.getByText("Indexé", { exact: true })).toBeVisible();
  await inspecteur.getByRole("searchbox", { name: "Chercher dans les passages indexés" }).fill("cobalt");
  await expect(inspecteur.locator(".mf-extraits")).toContainText("palette cobalt");
  await inspecteur.getByRole("button", { name: "Cadrage", exact: true }).click();
  await expect(page.getByRole("region", { name: "Passage cité" })).toContainText("palette cobalt");

  await page.goto("/v2/?vue=fichiers&fichier=" + cible);
  const contexte = inspecteur.getByRole("region", { name: "Contexte transmis à l’agent" });
  await contexte.getByText("Cadrage", { exact: true }).click();
  await expect(contexte).toContainText("palette cobalt");
  await contexte.getByRole("button", { name: "Ouvrir le passage cité" }).click();
  await expect(page.getByRole("region", { name: "Passage cité" })).toContainText("palette cobalt");
});

test("la démo distingue les sources de contexte et retourne à la note", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/v2/?demo=1&vue=fichiers&fichier=BO-demo-pdf");
  const inspecteur = page.getByRole("complementary", { name: "Inspecteur du fichier" });
  await expect(inspecteur.getByText("Entrant · Cadre du projet")).toBeVisible();
  await expect(page.locator('.mf-sommet[data-type="note"][data-contexte="true"]')).toBeVisible();
  const contexte = inspecteur.getByRole("region", { name: "Contexte transmis à l’agent" });
  await expect(contexte.getByText("Aperçu de démonstration")).toBeVisible();
  await contexte.getByText("Note de cadrage", { exact: true }).press("Enter");
  await contexte.getByRole("button", { name: "Ouvrir la source" }).click();
  await expect(inspecteur.getByRole("heading", { name: "Note de cadrage" })).toBeVisible();
  await expect(inspecteur.getByText("Sortant · Cadre du projet")).toBeVisible();
  await expect(inspecteur.getByText("Reprendre les missions en cours")).toBeVisible();
  expect(await page.locator('.mf-courant').first().evaluate((el) => getComputedStyle(el).display)).toBe("none");
});


test("une note lie le bon homonyme et son lien retour suit les modifications", async ({ page }) => {
  await ouvrir(page);
  await regler(page, { auto_analyse: false });
  const creerNote = async (titre: string, contenu: string, y: number) => {
    const r = await page.request.post("/api/v2/objets", { headers: { "X-Jarvis-Studio": "1" },
      data: { type: "note", contenu, x: 70, y, meta: { titre }, analyser: false } });
    expect(r.ok()).toBe(true);
    return (await r.json()).objet_id as string;
  };
  const origine = await creerNote("Journal de bord", "Voir la note.", 60);
  const homonyme = await creerNote("Décision", "L’autre note", 450);
  const cible = await creerNote("Décision", "La note à ouvrir", 840);
  await page.goto("/v2/?vue=fichiers&fichier=" + origine);
  const inspecteur = page.getByRole("complementary", { name: "Inspecteur du fichier" });
  await inspecteur.getByRole("button", { name: "Modifier la note" }).click();
  const zone = inspecteur.getByRole("textbox", { name: "Texte de la note" });
  await zone.fill("Voir [[Déc");
  const options = inspecteur.getByRole("listbox", { name: "Notes à lier" });
  await expect(options.getByRole("option")).toHaveCount(2);
  await options.getByRole("option").filter({ hasText: cible }).click();
  await expect(zone).toHaveValue("Voir [[" + cible + "|Décision]]");
  await inspecteur.getByRole("button", { name: "Enregistrer la note" }).click();
  await expect(inspecteur.getByRole("heading", { name: /Liens sortants/ })).toBeVisible();
  await expect(page.locator('.react-flow__edge[data-id="wiki:' + origine + ':' + cible + '"]')).toBeVisible();

  await page.reload();
  await inspecteur.getByRole("button", { name: "Décision", exact: true }).first().click();
  await expect(page).toHaveURL(new RegExp("fichier=" + cible));
  await expect(inspecteur).toContainText("La note à ouvrir");
  await expect(inspecteur.getByRole("heading", { name: /Liens retour/ })).toBeVisible();
  await inspecteur.getByRole("button", { name: "Journal de bord", exact: true }).click();
  await inspecteur.getByRole("button", { name: "Modifier la note" }).click();
  await zone.fill("Lien retiré.");
  await inspecteur.getByRole("button", { name: "Enregistrer la note" }).click();
  await expect(inspecteur.getByText("Lien retiré.", { exact: true })).toBeVisible();
  await expect(inspecteur.getByRole("heading", { name: /Liens sortants/ })).toHaveCount(0);
  await expect(page.locator('.react-flow__edge[data-id^="wiki:"]')).toHaveCount(0);
  await page.goto("/v2/?vue=fichiers&fichier=" + cible);
  await expect(inspecteur).toContainText("La note à ouvrir");
  await expect(inspecteur.getByRole("heading", { name: /Liens retour/ })).toHaveCount(0);
  await page.goto("/v2/?vue=fichiers&fichier=" + homonyme);
  await expect(inspecteur).toContainText("L’autre note");
  await expect(inspecteur.getByRole("heading", { name: /Liens retour/ })).toHaveCount(0);
});

test("indexer le texte réel d’un PDF paginé", async ({ page }) => {
  await ouvrir(page);
  await page.goto("/v2/?vue=fichiers");
  await page.locator('input[type="file"]').setInputFiles("public/demo/plan-produit.pdf");
  const inspecteur = page.getByRole("complementary", { name: "Inspecteur du fichier" });
  await expect(inspecteur.getByRole("heading", { name: "plan-produit.pdf", exact: true })).toBeVisible();
  const suite = inspecteur.getByRole("button", { name: "Page PDF suivante" });
  await expect(suite).toBeEnabled();
  await suite.click();
  await expect(inspecteur.getByText("Page 2 / 2")).toBeVisible();
  await inspecteur.getByRole("button", { name: "Indexer le fichier" }).click();
  await expect(inspecteur.getByText("Indexé", { exact: true })).toBeVisible();
  await inspecteur.getByRole("searchbox", { name: "Chercher dans les passages indexés" }).fill("Approbations humaines");
  await expect(inspecteur.locator(".mf-extraits")).toContainText("Approbations humaines");
});

test("les formats restent lisibles dans les deux thèmes et le carrousel ouvre le fichier choisi", async ({ page }) => {
  await page.goto("/v2/?demo=1&vue=fichiers");
  const carousel = page.getByRole("region", { name: "Fichiers récents" });
  const suivant = carousel.getByRole("button", { name: "Aperçu suivant" });
  const ouvrirApercu = carousel.getByRole("button", { name: /^Ouvrir l’aperçu de / });
  await expect(ouvrirApercu).toBeVisible();
  const premier = await ouvrirApercu.getAttribute("title");
  await suivant.press("ArrowRight");
  await expect(ouvrirApercu).not.toHaveAttribute("title", premier!);
  const titre = await ouvrirApercu.getAttribute("title");
  await ouvrirApercu.click();
  const inspecteur = page.getByRole("complementary", { name: "Inspecteur du fichier" });
  await expect(inspecteur.getByRole("heading", { name: titre!, exact: true })).toBeVisible();
  await expect(inspecteur).toBeFocused();

  const formats = page.getByRole("combobox", { name: "Type de fichier" });
  await expect(formats.getByRole("option", { name: "PDF", exact: true })).toHaveAttribute("value", "pdf");
  await expect(formats.getByRole("option", { name: "Image", exact: true })).toHaveAttribute("value", "image");
  for (const theme of ["jour", "nuit"]) {
    await page.getByRole("button", { name: `Passer au thème ${theme}` }).click();
    await formats.focus();
    const contrastes = await formats.evaluate((select) => {
      const luminance = (rgb: string) => (rgb.match(/\d+/g) ?? []).slice(0, 3)
        .map((value) => Number(value) / 255)
        .map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
        .reduce((total, value, index) => total + value * ([0.2126, 0.7152, 0.0722][index] ?? 0), 0);
      return [select, ...select.querySelectorAll("option")].map((element) => {
        const style = getComputedStyle(element);
        const foreground = luminance(style.color);
        const background = luminance(style.backgroundColor);
        return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
      });
    });
    expect(Math.min(...contrastes)).toBeGreaterThanOrEqual(4.5);
  }
  await formats.selectOption("pdf");
  await expect(page.locator(".mf-compte")).toContainText(/^1 fichier · \d+\/\d+ références$/);
});
