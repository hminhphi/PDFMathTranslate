"""High-level Office translation service.

Reuses the existing ``pdf2zh.translator`` implementations (and their
translation caches) so every configured service works for Office files
exactly as it does for PDFs.
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from asyncio import CancelledError
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from string import Template

import tqdm

from pdf2zh.office import docx_io, pptx_io, xlsx_io
from pdf2zh.office.ooxml import OoxmlPackage
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
    TencentTranslator,
    TLLMTranslator,
    X302AITranslator,
    XinferenceTranslator,
    ZhipuTranslator,
)

logger = logging.getLogger(__name__)

OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}

_PROCESSORS = {
    ".docx": docx_io,
    ".xlsx": xlsx_io,
    ".pptx": pptx_io,
}

_TRANSLATOR_CLASSES = {
    translator.name: translator
    for translator in [
        GoogleTranslator,
        BingTranslator,
        DeepLTranslator,
        DeepLXTranslator,
        OllamaTranslator,
        XinferenceTranslator,
        AzureOpenAITranslator,
        OpenAITranslator,
        ZhipuTranslator,
        ModelScopeTranslator,
        SiliconTranslator,
        GeminiTranslator,
        AzureTranslator,
        TencentTranslator,
        DifyTranslator,
        AnythingLLMTranslator,
        ArgosTranslator,
        GrokTranslator,
        GroqTranslator,
        DeepseekTranslator,
        MiniMaxTranslator,
        OpenAIlikedTranslator,
        QwenMtTranslator,
        TLLMTranslator,
        X302AITranslator,
    ]
}


def is_office_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in OFFICE_EXTENSIONS


def build_translator(
    service: str,
    lang_in: str,
    lang_out: str,
    envs: dict | None = None,
    prompt: Template | None = None,
    ignore_cache: bool = False,
):
    name, separator, model = service.partition(":")
    translator_class = _TRANSLATOR_CLASSES.get(name)
    if translator_class is None:
        raise ValueError(f"Unsupported translation service: {service}")
    return translator_class(
        lang_in,
        lang_out,
        model if separator else "",
        envs=envs,
        prompt=prompt,
        ignore_cache=ignore_cache,
    )


def _has_translatable_text(text: str) -> bool:
    return any(unicodedata.category(char).startswith("L") for char in text)


def translate_units(
    units,
    translator,
    thread: int = 4,
    callback=None,
    cancellation_event: asyncio.Event | None = None,
) -> list[str]:
    texts = [unit.marked_text for unit in units]
    results: list[str] = list(texts)

    def work(text: str) -> str:
        if cancellation_event and cancellation_event.is_set():
            raise CancelledError("task cancelled")
        if not _has_translatable_text(text):
            return text
        translated = translator.translate(text)
        if translated is None or not translated.strip():
            return text
        return translated

    with tqdm.tqdm(total=len(units), desc="Translating") as progress:
        with ThreadPoolExecutor(max_workers=max(1, thread)) as executor:
            futures = {
                executor.submit(work, text): index for index, text in enumerate(texts)
            }
            for future in as_completed(futures):
                index = futures[future]
                results[index] = future.result()
                progress.update(1)
                if callback:
                    callback(progress)
    return results


def translate_office_file(
    path: str | Path,
    lang_in: str,
    lang_out: str,
    service: str,
    thread: int = 4,
    output: str | Path = "",
    envs: dict | None = None,
    prompt: Template | None = None,
    ignore_cache: bool = False,
    callback=None,
    cancellation_event: asyncio.Event | None = None,
    translator=None,
) -> Path:
    path = Path(path)
    processor = _PROCESSORS.get(path.suffix.lower())
    if processor is None:
        raise ValueError(f"Unsupported Office format: {path.suffix}")

    if translator is None:
        translator = build_translator(
            service,
            lang_in,
            lang_out,
            envs=envs,
            prompt=prompt,
            ignore_cache=ignore_cache,
        )

    package = OoxmlPackage.load(path)
    units = processor.extract_units(package)
    if not units:
        raise ValueError(f"No translatable text found in {path.name}")

    logger.info(
        "Office translation: %s (%d units, %s -> %s, service=%s)",
        path.name,
        len(units),
        lang_in,
        lang_out,
        service,
    )
    translations = translate_units(
        units,
        translator,
        thread=thread,
        callback=callback,
        cancellation_event=cancellation_event,
    )

    changed_parts: set[str] = set()
    exact = 0
    fallback = 0
    for unit, translated in zip(units, translations):
        if translated == unit.marked_text:
            continue
        if unit.apply_translation(translated):
            exact += 1
        else:
            fallback += 1
        changed_parts.add(unit.part)

    if fallback:
        logger.info(
            "Run markers preserved for %d units; proportional fallback for %d",
            exact,
            fallback,
        )

    output_dir = Path(output) if output else Path(".")
    output_path = output_dir / f"{path.stem}-translated{path.suffix.lower()}"
    saved = package.save(output_path, changed_parts)
    logger.info("Saved translated Office file: %s", saved)
    return saved
