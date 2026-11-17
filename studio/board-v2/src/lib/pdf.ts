export async function moteurPdf() {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = (await import("pdfjs-dist/build/pdf.worker.min.mjs?url")).default;
  return pdfjs;
}


export async function extraireTextePdf(url: string): Promise<string> {
  const pdf = await moteurPdf();
  const chargement = pdf.getDocument({ url, withCredentials: true });
  const timer = window.setTimeout(() => void chargement.destroy().catch(() => undefined), 10_000);
  const maximum = 15_000; // reste sous la limite JSON du Studio même avec des caractères multioctets
  let texte = "";
  try {
    const doc = await chargement.promise;
    for (let i = 1; i <= Math.min(24, doc.numPages) && texte.length < maximum; i++) {
      const page = await doc.getPage(i);
      const contenu = await page.getTextContent();
      const lignes = contenu.items.flatMap((item) => "str" in item ? [item.str + (item.hasEOL ? "\n" : " ")] : []).join("").trim();
      if (lignes) texte += `## Page ${i}\n${lignes}\n\n`;
      page.cleanup();
    }
    return texte.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "").slice(0, maximum).trim();
  } finally {
    window.clearTimeout(timer);
    await chargement.destroy().catch(() => undefined);
  }
}
