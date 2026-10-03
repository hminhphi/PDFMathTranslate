<div align="center">

<img src="./docs/images/banner.png" width="320px" alt="PDF2ZH"/>

<h2>PDFMathTranslate</h2>

**Scientific PDF and Office document translation with preserved layouts**

[简体中文](docs/README_zh-CN.md) | [繁體中文](docs/README_zh-TW.md) | [日本語](docs/README_ja-JP.md) | [한국어](docs/README_ko-KR.md) | English

<p>
  <a href="https://pypi.org/project/pdf2zh/"><img src="https://img.shields.io/pypi/v/pdf2zh"></a>
  <a href="https://github.com/Byaidu/PDFMathTranslate"><img src="https://img.shields.io/badge/upstream-Byaidu%2FPDFMathTranslate-blue"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/Byaidu/PDFMathTranslate"></a>
  <a href="https://github.com/Byaidu/PDFMathTranslate/pulls"><img src="https://img.shields.io/badge/contributions-welcome-green"></a>
</p>

</div>

---

## 1. What does this do?

Translate scientific and technical documents while keeping their layout intact:

- **PDF** — formulas, figures, tables, captions and table of contents keep their
  original positions. Layout detection (DocLayout-YOLO), formula-aware text
  extraction (pdfminer) and precise re-typesetting produce `-mono` and `-dual`
  PDFs.
- **Office** — `.docx`, `.xlsx` and `.pptx` are translated **in place**: text is
  replaced inside the OOXML package so formatting, tables, text boxes, charts
  and speaker notes stay untouched. No LibreOffice round-trip required.
- **Web UI** — a viewer-first workspace (single / compare / overlay, search,
  thumbnails, dark mode) for configuring, running and inspecting translations.
- **Local translation LLMs** — a dedicated `tllm` service speaks the native
  prompt formats of HY-MT1.5, TranslateGemma, Hunyuan-MT and Seed-X served by
  LM Studio, llama.cpp, vLLM or Ollama.

> This repository is a downstream fork of
> [Byaidu/PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate) that adds
> Office support, the local translation-LLM service and the new web interface.
> See [section 7](#7-differences-from-upstream) for details.

---

## 2. Installation

Python `3.11 <= version <= 3.12` is required.

### 2.1 Using uv (recommended)

```bash
pip install uv
uv tool install --python 3.12 pdf2zh
```

### 2.2 Using pip

```bash
pip install pdf2zh
```

### 2.3 From this checkout

```bash
uv pip install -e .
# or: pip install -e .
```

For OCR of scanned pages add the optional extra:

```bash
uv pip install -e '.[ocr]'
```

---

## 3. Quick start

### 3.1 Command line

```bash
# PDF: writes paper-mono.pdf and paper-dual.pdf to the current directory
pdf2zh paper.pdf -li en -lo vi

# Office: writes report-translated.docx (format preserved)
pdf2zh report.docx -li en -lo vi

# Spreadsheet / slides
pdf2zh budget.xlsx -li en -lo vi
pdf2zh deck.pptx  -li en -lo vi

# A local translation LLM (see section 5)
pdf2zh paper.pdf -li en -lo vi -s tllm

# Translate a whole directory
pdf2zh --dir ./papers -o ./translated
```

### 3.2 Web UI

```bash
pdf2zh -i
```

The browser opens at `http://localhost:7860/`. The workspace lets you:

- drop a PDF/DOCX/XLSX/PPTX or paste a document URL;
- pick languages, service, page range and advanced options;
- watch progress and cancel a running job;
- inspect the result in **Single**, **Compare** (source vs translated) or
  **Overlay** mode with search, zoom, thumbnails and focus mode;
- download mono/dual PDFs or the translated Office file.

Use a custom port with `pdf2zh -i --serverport 8080`. The legacy Gradio
interface is still available via `pdf2zh -i --gradio`.

---

## 4. Translation services

| Service | Notes |
| --- | --- |
| Google / Bing | Free, no key required |
| DeepL / DeepLX / Azure | API key required |
| OpenAI / AzureOpenAI / Grok / Groq / DeepSeek / Gemini / MiniMax / Zhipu / ModelScope / Silicon / 302.AI | OpenAI-compatible LLM endpoints |
| Ollama / Xinference / OpenAI-liked / Dify / AnythingLLM | Self-hosted endpoints |
| Tencent / Ali Qwen-Translation | Cloud translation APIs |
| Argos Translate | Fully offline, install `pdf2zh[argostranslate]` |
| **TLLM (Local)** | Local translation LLMs — HY-MT1.5, TranslateGemma, Hunyuan-MT, Seed-X (section 5) |

API keys and endpoints are stored in
`~/.config/PDFMathTranslate/config.json` (or `%USERPROFILE%\.config\PDFMathTranslate\config.json`
on Windows). Every option can also be supplied through environment variables.

---

## 5. Local translation LLMs (`tllm` service)

General chat LLMs and dedicated translation LLMs use different prompts,
sampling defaults and language tags. The `tllm` service handles those
differences automatically.

### 5.1 Serve a model

| Runtime | Command |
| --- | --- |
| **LM Studio** (Windows/macOS) | Load `hy-mt1.5-1.8b` (GGUF) and start the local server on port 8080 |
| **llama.cpp** | `llama-server -hf tencent/HY-MT1.5-1.8B-GGUF:Q8_0 --jinja -c 4096 -ngl 99` |
| **vLLM** | `vllm serve tencent/HY-MT1.5-1.8B --trust-remote-code` |
| **Ollama** | `ollama pull translategemma:12b` |

Both the OpenAI-compatible API (`/v1/chat/completions`) and the LM Studio
native API (`/api/v1/chat`) are supported and auto-detected from the base URL.

### 5.2 Configure

| Variable | Meaning | Default |
| --- | --- | --- |
| `TLLM_BASE_URL` | Server root. Add `/api` to force the LM Studio native API | `http://127.0.0.1:8080` |
| `TLLM_API_KEY` | Bearer token (any value for local servers) | `local` |
| `TLLM_MODEL` | Model name as served | `hy-mt1.5-1.8b` |
| `TLLM_PRESET` | `hy-mt`, `hunyuan-mt`, `translategemma`, `seed-x` or `custom` | `hy-mt` |
| `TLLM_GLOSSARY` | Terminology pairs, e.g. `gradient=đạo hàm;tensor=ten-xơ` | – |
| `TLLM_TEMPLATE` | Prompt template used when `TLLM_PRESET=custom` (`{lang_out_name}`, `{text}`) | – |

Set them in the web UI service fields, in `config.json`, or as environment
variables:

```bash
# Windows PowerShell
$env:TLLM_BASE_URL = "http://127.0.0.1:8080"
$env:TLLM_MODEL = "hy-mt1.5-1.8b"
pdf2zh paper.pdf -li en -lo vi -s tllm
```

### 5.3 Behaviour worth knowing

- Presets use the models' official sampling defaults (HY-MT: `temperature=0.7`,
  `top_p=0.6`, `top_k=20`, `repeat_penalty=1.05`; TranslateGemma: greedy).
- Full language names are generated automatically (`vi` → `Vietnamese`,
  `zh-TW` → `Traditional Chinese`).
- Formula placeholders (`{v0}`) and Office run markers (`[[R0]]…[[/R0]]`) are
  preserved via a dynamically built instruction. The instruction only mentions
  marker kinds that actually occur, because naming absent placeholders makes
  small models hallucinate them.
- Glossary injection is skipped for text that contains run markers; 1.8B models
  lose marker fidelity when both are combined. Plain paragraphs still receive
  the glossary.
- Run markers that small models mangle (`[R0]`, `[/R0]`) are parsed
  tolerantly, and stray fragments are cleaned from the output.

---

## 6. Office translation details

| Format | Coverage |
| --- | --- |
| `.docx` | Body, tables, headers/footers, footnotes/endnotes, comments, content controls, hyperlinks, text boxes (`w:txbxContent`), tabs and field placeholders |
| `.pptx` | Slides, grouped shapes, tables, charts, diagram data, speaker notes |
| `.xlsx` | Shared strings, inline strings, drawing text boxes, chart titles. **Formula cells (`f`) and cached values (`v`) are never touched** |

How it works:

1. the OOXML package is unzipped and each paragraph / string item is collected
   with its run structure;
2. runs are joined into one marked string (`[[R0]]…[[/R0]]`) so the translator
   can reorder text while keeping run boundaries;
3. translation goes through the regular pdf2zh services (cache included);
4. each translated run is written back into its original text node; when the
   translator drops the markers, the text is distributed proportionally across
   the original runs;
5. every untouched part of the package is copied byte-for-byte.

Output files are named `<name>-translated.<ext>`. Old binary `.doc` files are
still converted to PDF through LibreOffice.

---

## 7. Differences from upstream

- **Office documents** are translated in place (upstream converts `.docx` to PDF
  and loses editability).
- **`tllm` service** for local translation LLMs with official prompt templates,
  sampling defaults, glossary support and marker preservation.
- **New viewer-first web UI** (`pdf2zh -i`); the original Gradio interface is
  available via `--gradio`.
- **Vietnamese** is available in the GUI/CLI language lists, and Vietnamese
  font handling on Windows picks a serif font with full diacritic coverage and
  a valid OpenType `post` table for font subsetting.

---

## 8. Advanced options

| Option | Function | Example |
| --- | --- | --- |
| `files` | Local files | `pdf2zh ~/local.pdf` |
| `links` | Online files | `pdf2zh http://arxiv.org/paper.pdf` |
| `-i` | Web UI | `pdf2zh -i` |
| `--gradio` | Legacy Gradio UI | `pdf2zh -i --gradio` |
| `-p` | Partial document translation | `pdf2zh example.pdf -p 1` |
| `-li` | Source language | `pdf2zh example.pdf -li en` |
| `-lo` | Target language | `pdf2zh example.pdf -lo zh` |
| `-s` | Translation service | `pdf2zh example.pdf -s tllm` |
| `-t` | Threads | `pdf2zh example.pdf -t 1` |
| `-o` | Output directory | `pdf2zh example.pdf -o output` |
| `-f`, `-c` | Formula font/char exceptions | `pdf2zh example.pdf -f "(MS.*)"` |
| `-cp` | Compatibility mode | `pdf2zh example.pdf --compatible` |
| `--skip-subset-fonts` | Skip font subsetting | `pdf2zh example.pdf --skip-subset-fonts` |
| `--ignore-cache` | Ignore the translation cache | `pdf2zh example.pdf --ignore-cache` |
| `--prompt` | Custom LLM prompt | `pdf2zh --prompt prompt.txt` |
| `--onnx` | Custom DocLayout-YOLO model | `pdf2zh --onnx onnx/model/path` |
| `--serverport` | Web UI port | `pdf2zh -i --serverport 7860` |
| `--dir` | Batch translate a directory | `pdf2zh --dir /path/to/translate/` |
| `--config` | Custom config file | `pdf2zh --config /path/to/config.json` |
| `--mode` | `fast` (default) or `precise` (experimental v2 kernel) | `pdf2zh --mode precise example.pdf` |
| `--babeldoc` | Experimental BabelDOC backend | `pdf2zh --babeldoc -s openai example.pdf` |
| `--mcp` | MCP STDIO mode | `pdf2zh --mcp` |
| `--sse` | MCP SSE mode | `pdf2zh --mcp --sse` |

Network-restricted regions can mirror the layout model download:

```bash
set HF_ENDPOINT=https://hf-mirror.com        # cmd
$env:HF_ENDPOINT = "https://hf-mirror.com"   # PowerShell
```

---

## 9. Python API

Use `pdf2zh` from other Python programs:

```python
from pdf2zh.high_level import translate

translate(files=["paper.pdf"], lang_in="en", lang_out="vi", service="google")
```

See [docs/APIS.md](./docs/APIS.md) for the full API reference and the HTTP API.

---

## 10. Development

```bash
uv pip install -e .
uv run --no-sync python -m pytest test/ -q
uv run --no-sync black pdf2zh test
uv run --no-sync flake8 pdf2zh test
```

The web UI lives in `pdf2zh/webui/` (FastAPI backend + static viewer) and the
Office pipeline in `pdf2zh/office/`.

---

## 11. Acknowledgements

- Upstream engine: [Byaidu/PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate)
- New backend: [BabelDOC](https://github.com/funstory-ai/BabelDOC)
- Document merging: [PyMuPDF](https://github.com/pymupdf/PyMuPDF)
- Document parsing: [pdfminer.six](https://github.com/pdfminer/pdfminer.six)
- Layout parsing: [DocLayout-YOLO](https://github.com/opendatalab/DocLayout-YOLO)
- Document preview: [Gradio PDF](https://github.com/freddyaboulton/gradio-pdf)
- Multilingual font: [Go Noto Universal](https://github.com/satbyy/go-noto-universal)
- Office write-back pipeline inspired by
  [sanmu6-public](https://github.com/daodiaonan/sanmu6-public) and
  [pptx-translate](https://github.com/Vncntvx/pptx-translate) (both MIT)
- Local translation LLMs: [HY-MT](https://github.com/Tencent-Hunyuan/HY-MT),
  [TranslateGemma](https://huggingface.co/google/translategemma-4b-it)

## 12. Citation

This work was accepted at the *Proceedings of the 2025 Conference on Empirical
Methods in Natural Language Processing: System Demonstrations* (EMNLP 2025).

```bibtex
@inproceedings{ouyang-etal-2025-pdfmathtranslate,
  title = "{PDFM}ath{T}ranslate: Scientific Document Translation Preserving Layouts",
  author = "Ouyang, Rongxin and Chu, Chang and Xin, Zhikuang and Ma, Xiangyao",
  booktitle = "Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing: System Demonstrations",
  month = nov,
  year = "2025",
  publisher = "Association for Computational Linguistics",
  pages = "918--924",
  url = "https://aclanthology.org/2025.emnlp-demos.71/"
}
```

## 13. License

[AGPL-3.0](./LICENSE) — the same license as the upstream project.
