export async function pdfThumbnail(file: File): Promise<Blob | null> {
  const { getDocument, PDFWorker } = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const data = new Uint8Array(await file.arrayBuffer());
  const port = new Worker(new URL("pdfjs-dist/legacy/build/pdf.worker.min.mjs", import.meta.url), { type: "module" });
  const worker = PDFWorker.create({ port });
  const task = getDocument({ data, worker, stopAtErrors: true });

  async function renderFirstPage() {
    const pdf = await task.promise;
    const page = await pdf.getPage(1);
    const original = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: 480 / Math.max(original.width, original.height) });
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.ceil(viewport.width));
    canvas.height = Math.max(1, Math.ceil(viewport.height));
    await page.render({ canvas, viewport }).promise;
    return new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  }

  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const fallback = new Promise<null>((resolve) => {
      timer = setTimeout(() => resolve(null), 8000);
      port.addEventListener("error", () => resolve(null), { once: true });
    });
    return await Promise.race([renderFirstPage(), fallback]);
  } finally {
    clearTimeout(timer);
    void task.destroy().catch(() => {});
    worker.destroy();
    port.terminate();
  }
}
