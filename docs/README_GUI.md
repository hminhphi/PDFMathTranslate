# Web UI

This subfolder documents the graphical interface of `pdf2zh`.

## Usage

1. Run `pdf2zh -i` (or double-click `pdf2zh.exe` in the portable Windows build).
2. Drop a PDF, DOCX, XLSX or PPTX file (or paste a link) into the sidebar.
3. Pick languages, service and options, then press **Translate**.
4. Inspect the result in the viewer and download the output.

The browser opens at <http://localhost:7860>. Use a custom port with
`pdf2zh -i --serverport 8080`.

## Features

- **Viewer-first workspace** — thumbnails, page navigation, zoom and fit-width.
- **Single / Compare / Overlay** — inspect the source page, the translated page
  side by side, or the translation overlaid on the original with an opacity
  slider.
- **Search** — find terms across the document and jump between matches.
- **Focus mode** — full-screen reading without the chrome.
- **Live progress and cancel** for running jobs.
- **Light and dark themes**, remembered per browser.
- **Downloads** — mono/dual PDFs for PDF input, the translated file for Office
  input.

For Office documents (`.docx`, `.xlsx`, `.pptx`) the translation happens in
place and preserves formatting, tables, text boxes, charts and speaker notes;
the viewer preview is available for PDF files only.

## Environment Variables

You can set the default source and target languages:

- `PDF2ZH_LANG_FROM`: Sets the source language. Defaults to "English".
- `PDF2ZH_LANG_TO`: Sets the target language. Defaults to "Simplified Chinese".

## Supported Languages

The following languages are supported:

- English
- Simplified Chinese
- Traditional Chinese
- French
- German
- Japanese
- Korean
- Russian
- Spanish
- Italian
- Vietnamese

## Legacy Gradio interface

The previous Gradio interface is still available via `pdf2zh -i --gradio`.

## Preview

<img src="./images/before.png" width="500"/>
<img src="./images/after.png" width="500"/>
