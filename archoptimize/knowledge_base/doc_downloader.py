"""Download source PDFs once into a local cache folder (gitignored)."""

from __future__ import annotations

from pathlib import Path

import httpx

from archoptimize.knowledge_base.knowledge_sources import KnowledgeSource

MAX_PDF_BYTES = 50 * 1024 * 1024


def download_source(source: KnowledgeSource, cache_dir: Path, *, force: bool = False) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / source.file_name
    if target.exists() and not force:
        return target
    with httpx.stream("GET", source.url, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        if "pdf" not in resp.headers.get("content-type", ""):
            raise ValueError(f"{source.url} did not return a PDF")
        data = b""
        for part in resp.iter_bytes():
            data += part
            if len(data) > MAX_PDF_BYTES:
                raise ValueError(f"{source.url} is larger than {MAX_PDF_BYTES} bytes")
    tmp = target.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(target)  # only a complete file ever gets the final name
    return target
