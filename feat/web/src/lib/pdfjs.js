import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

GlobalWorkerOptions.workerSrc = workerUrl;

export function openPdf(url) {
  return getDocument({
    url,
    cMapUrl: '/assets/pdfjs/cmaps/',
    standardFontDataUrl: '/assets/pdfjs/standard_fonts/',
    cMapPacked: true,
    isEvalSupported: false,
    useWasm: false,
    disableFontFace: true,
  });
}
