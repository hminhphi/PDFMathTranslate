"""MIPI BookTrans web UI — viewer-first interface for pdf2zh.

Serves the static prototype interface and exposes a small JSON API on top
of the existing translation kernel (PDF and Office pipelines).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pdf2zh import __version__
from pdf2zh.config import ConfigManager
from pdf2zh.translator import (
    AnythingLLMTranslator,
    ArgosTranslator,
    AzureOpenAITranslator,
    AzureTranslator,
    BingTranslator,
    DeepLTranslator,
    DeepLXTranslator,
    DeepseekTranslator,
    DifyTranslator,
    GeminiTranslator,
    GoogleTranslator,
    GrokTranslator,
    GroqTranslator,
    MiniMaxTranslator,
    ModelScopeTranslator,
    OllamaTranslator,
    OpenAIlikedTranslator,
    OpenAITranslator,
    QwenMtTranslator,
    SiliconTranslator,
    TLLMTranslator,
    TencentTranslator,
    X302AITranslator,
    XinferenceTranslator,
    ZhipuTranslator,
)

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
WORK_DIR = Path("pdf2zh_files_web")

SERVICE_MAP = {
    "Google": GoogleTranslator,
    "Bing": BingTranslator,
    "DeepL": DeepLTranslator,
    "DeepLX": DeepLXTranslator,
    "Ollama": OllamaTranslator,
    "Xinference": XinferenceTranslator,
    "AzureOpenAI": AzureOpenAITranslator,
    "OpenAI": OpenAITranslator,
    "Zhipu": ZhipuTranslator,
    "ModelScope": ModelScopeTranslator,
    "Silicon": SiliconTranslator,
    "Gemini": GeminiTranslator,
    "Azure": AzureTranslator,
    "Tencent": TencentTranslator,
    "Dify": DifyTranslator,
    "AnythingLLM": AnythingLLMTranslator,
    "Argos Translate": ArgosTranslator,
    "Grok": GrokTranslator,
    "Groq": GroqTranslator,
    "DeepSeek": DeepseekTranslator,
    "MiniMax": MiniMaxTranslator,
    "OpenAI-liked": OpenAIlikedTranslator,
    "Ali Qwen-Translation": QwenMtTranslator,
    "TLLM (Local)": TLLMTranslator,
    "302.AI": X302AITranslator,
}

LANG_MAP = {
    "Simplified Chinese": "zh",
    "Traditional Chinese": "zh-TW",
    "English": "en",
    "French": "fr",
    "German": "de",
    "Japanese": "ja",
    "Korean": "ko",
    "Russian": "ru",
    "Spanish": "es",
    "Italian": "it",
    "Vietnamese": "vi",
}

PAGE_MAP = {
    "All": None,
    "First": [0],
    "First 5 pages": list(range(0, 5)),
    "Others": None,
}

_ENV_LABELS = {
    "API_KEY": "API key",
    "AUTH_KEY": "API key",
    "ACCESS_TOKEN": "Access token",
    "SECRET_ID": "Secret ID",
    "SECRET_KEY": "Secret key",
    "BASE_URL": "Base URL",
    "ENDPOINT": "Endpoint",
    "HOST": "Host",
    "URL": "URL",
    "MODEL": "Model",
    "APIKEY": "API key",
    "GLOSSARY": "Glossary (term=translation; ...)",
    "PRESET": "Preset (hy-mt | hunyuan-mt | translategemma | seed-x | custom)",
    "TEMPLATE": "Custom template",
    "STREAM": "Stream (true/false)",
    "STOP_TOKENS": "Stop tokens",
    "MAX_TOKENS": "Max tokens",
    "DOMAINS": "Domains",
}


def _env_label(key: str) -> str:
    for marker, label in _ENV_LABELS.items():
        if key.endswith(marker) or marker in key:
            return label
    return key.replace("_", " ").title()


def _env_is_secret(key: str) -> bool:
    upper = key.upper()
    return "KEY" in upper or "TOKEN" in upper or "SECRET" in upper


def _service_metadata() -> list[dict]:
    services = []
    for label, translator in SERVICE_MAP.items():
        envs = []
        for key, default in translator.envs.items():
            envs.append(
                {
                    "key": key,
                    "label": _env_label(key),
                    "default": "" if default is None else str(default),
                    "secret": _env_is_secret(key),
                    "value": ConfigManager.get_env_by_translatername(
                        translator, key, "" if default is None else str(default)
                    ),
                }
            )
        services.append(
            {
                "label": label,
                "name": translator.name,
                "custom_prompt": bool(getattr(translator, "CustomPrompt", False)),
                "envs": envs,
            }
        )
    return services


@dataclass
class Job:
    id: str
    output_dir: Path
    source_name: str = ""
    state: str = "queued"
    progress: float = 0.0
    status: str = "Queued"
    error: str = ""
    outputs: dict = field(default_factory=dict)
    cancellation: asyncio.Event = field(default_factory=asyncio.Event)
    thread: Optional[threading.Thread] = None


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()


def _parse_pages(selected: str, page_input: str) -> Optional[list[int]]:
    if selected != "Others":
        return PAGE_MAP.get(selected)
    pages: list[int] = []
    for chunk in page_input.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = chunk.split("-", 1)
            pages.extend(range(int(start) - 1, int(end)))
        else:
            pages.append(int(chunk) - 1)
    return pages


def _collect_outputs(job: Job, source_path: Path) -> dict:
    stem = source_path.stem
    candidates = {
        "mono": job.output_dir / f"{stem}-mono.pdf",
        "dual": job.output_dir / f"{stem}-dual.pdf",
        "translated": job.output_dir / f"{stem}-translated{source_path.suffix.lower()}",
    }
    return {kind: str(path) for kind, path in candidates.items() if path.exists()}


def _run_translation(job: Job, params: dict) -> None:
    from pdf2zh.kernel import KernelRegistry
    from pdf2zh.kernel.protocol import TranslateRequest

    try:
        job.state = "running"
        job.status = "Reading document…"
        KernelRegistry.switch(params["mode"])
        kernel = KernelRegistry.get()

        def progress_callback(progress) -> None:
            total = getattr(progress, "total", 0) or 0
            current = getattr(progress, "n", 0) or 0
            if total:
                job.progress = min(0.99, current / total)
            desc = getattr(progress, "desc", "") or "Translating…"
            job.status = desc

        request = TranslateRequest(
            files=[str(params["source_path"])],
            output=str(job.output_dir),
            pages=params["pages"],
            lang_in=params["lang_in"],
            lang_out=params["lang_out"],
            service=params["service_name"],
            thread=params["thread"],
            envs=params["envs"],
            prompt=params["prompt"],
            skip_subset_fonts=params["skip_fonts"],
            ignore_cache=params["ignore_cache"],
            vfont=params["vfont"],
            compatible=False,
        )
        kernel.translate(
            request,
            callback=progress_callback,
            cancellation_event=job.cancellation,
        )
        job.outputs = _collect_outputs(job, params["source_path"])
        if not job.outputs:
            raise RuntimeError("Translation produced no output files")
        job.progress = 1.0
        job.state = "done"
        job.status = "Translation complete"
    except asyncio.CancelledError:
        job.state = "cancelled"
        job.status = "Translation cancelled"
    except Exception as error:  # noqa: BLE001
        logger.exception("Web translation job failed")
        job.state = "error"
        job.error = str(error)
        job.status = "Translation failed"


app = FastAPI(title="MIPI BookTrans", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/meta")
def api_meta() -> JSONResponse:
    try:
        from babeldoc import __version__ as babeldoc_version
    except Exception:  # noqa: BLE001
        babeldoc_version = ""
    return JSONResponse(
        {
            "version": __version__,
            "babeldoc_version": babeldoc_version,
            "services": _service_metadata(),
            "languages": LANG_MAP,
            "defaults": {
                "lang_from": ConfigManager.get("PDF2ZH_LANG_FROM", "English"),
                "lang_to": ConfigManager.get("PDF2ZH_LANG_TO", "Simplified Chinese"),
                "service": ConfigManager.get("PDF2ZH_SERVICE", ""),
            },
        }
    )


def _download_link(url: str, destination: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                handle.write(chunk)


@app.post("/api/translate")
async def api_translate(
    file: Optional[UploadFile] = None,
    link: str = Form(""),
    service: str = Form("Google"),
    lang_from: str = Form("English"),
    lang_to: str = Form("Simplified Chinese"),
    pages: str = Form("All"),
    page_input: str = Form(""),
    threads: str = Form("4"),
    mode: str = Form("fast"),
    skip_fonts: str = Form(""),
    ignore_cache: str = Form(""),
    vfont: str = Form(""),
    prompt: str = Form(""),
    envs: str = Form("{}"),
) -> JSONResponse:
    translator = SERVICE_MAP.get(service)
    if translator is None:
        raise HTTPException(status_code=400, detail="Unknown service")
    if lang_from not in LANG_MAP or lang_to not in LANG_MAP:
        raise HTTPException(status_code=400, detail="Unknown language")

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    if file is not None and file.filename:
        source_name = Path(file.filename).name
        source_path = job_dir / source_name
        with source_path.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    elif link.strip():
        source_name = Path(link.strip().split("?")[0]).name or "document.pdf"
        source_path = job_dir / source_name
        try:
            _download_link(link.strip(), source_path)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(
                status_code=400, detail=f"Could not download the link: {error}"
            ) from error
    else:
        raise HTTPException(status_code=400, detail="No file or link provided")

    try:
        page_list = _parse_pages(pages, page_input)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid page range") from error

    env_map = json.loads(envs or "{}")
    env_map = {str(key): str(value) for key, value in env_map.items() if value}

    try:
        thread_count = max(1, min(32, int(threads)))
    except ValueError:
        thread_count = 4

    job = Job(id=job_id, output_dir=job_dir, source_name=source_name)

    params = {
        "source_path": source_path,
        "pages": page_list,
        "lang_in": LANG_MAP[lang_from],
        "lang_out": LANG_MAP[lang_to],
        "service_name": translator.name,
        "thread": thread_count,
        "envs": env_map,
        "prompt": prompt.strip() or None,
        "skip_fonts": bool(skip_fonts),
        "ignore_cache": bool(ignore_cache),
        "vfont": vfont,
        "mode": mode if mode in ("fast", "precise") else "fast",
    }

    ConfigManager.set("PDF2ZH_SERVICE", service)
    ConfigManager.set("PDF2ZH_LANG_FROM", lang_from)
    ConfigManager.set("PDF2ZH_LANG_TO", lang_to)

    with JOBS_LOCK:
        JOBS[job_id] = job
    job.thread = threading.Thread(
        target=_run_translation, args=(job, params), daemon=True
    )
    job.thread.start()
    return JSONResponse({"job_id": job_id})


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return JSONResponse(
        {
            "id": job.id,
            "state": job.state,
            "progress": job.progress,
            "status": job.status,
            "error": job.error,
            "outputs": job.outputs,
            "source_name": job.source_name,
        }
    )


@app.post("/api/jobs/{job_id}/cancel")
def api_cancel(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    job.cancellation.set()
    return JSONResponse({"ok": True})


@app.get("/api/jobs/{job_id}/file/{kind}")
def api_file(job_id: str, kind: str) -> FileResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    path = job.outputs.get(kind)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="File not available")
    return FileResponse(path, filename=Path(path).name)


@app.get("/api/jobs/{job_id}/preview/{side}")
def api_preview(job_id: str, side: str) -> FileResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    if side == "source":
        path = job.output_dir / job.source_name
    elif side == "translated":
        path = Path(job.outputs.get("mono", ""))
    else:
        raise HTTPException(status_code=400, detail="Unknown preview side")
    if not path or not Path(path).exists() or Path(path).suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="Preview not available")
    return FileResponse(path, media_type="application/pdf")


def run_server(
    server_port: int = 7860,
    server_name: str = "0.0.0.0",
    open_browser: bool = True,
) -> None:
    import uvicorn

    if open_browser:
        threading.Timer(
            1.5, lambda: webbrowser.open(f"http://localhost:{server_port}")
        ).start()
    uvicorn.run(app, host=server_name, port=server_port, log_level="info")


def main() -> None:
    run_server()


if __name__ == "__main__":
    main()
