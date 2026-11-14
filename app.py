import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from typing import Literal
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from converter import convert_pdf
from compiler import CompileError, compile_latex

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 20 * 1024 * 1024
app = FastAPI(title="PDF3TeX", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
conversion_lock = asyncio.Lock()
compile_lock = asyncio.Lock()


class CompileRequest(BaseModel):
    tex: str = Field(min_length=1, max_length=2_000_000)
    project_zip: str = Field(default='', max_length=70_000_000)
    original_pdf: str = Field(default='', max_length=28_000_000)
    engine: Literal['tectonic', 'pdflatex'] = 'tectonic'
    fidelity_target: Literal[90, 95] = 95


@app.post('/api/compile')
async def compile_document(request: CompileRequest):
    if compile_lock.locked():
        raise HTTPException(429, 'Another document is compiling. Please try again shortly.')
    async with compile_lock:
        try:
            task = asyncio.create_task(asyncio.to_thread(compile_latex, request.tex, request.project_zip, request.original_pdf, request.engine))
            try:
                result = await asyncio.shield(task)
                if 'comparison' in result:
                    result['comparison']['target'] = request.fidelity_target
                    result['comparison']['matches'] = result['comparison']['similarity'] >= request.fidelity_target
                return result
            except asyncio.CancelledError:
                await task
                raise
        except CompileError as exc:
            raise HTTPException(exc.status, {'message': str(exc), 'log': exc.log}) from exc
        except Exception as exc:
            logging.exception('LaTeX compilation failed')
            raise HTTPException(500, {'message': 'The compiler could not complete the request.', 'log': ''}) from exc


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "readable / layout reconstruction"}


@app.post("/api/convert")
async def convert(file: UploadFile = File(...), mode: Literal['readable', 'layout'] = Form('readable')):
    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Choose a PDF file.")
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "The PDF must be smaller than 20 MB.")
        if not data or b"%PDF-" not in data[:1024]:
            raise HTTPException(400, "This file is not a valid PDF.")
        if conversion_lock.locked():
            raise HTTPException(429, "Another PDF is being converted. Please try again shortly.")
        async with conversion_lock:
            try:
                # Shield ensures a disconnected client cannot release the lock
                # while the underlying conversion worker is still running.
                task = asyncio.create_task(asyncio.to_thread(convert_pdf, data, Path(file.filename).name, mode))
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            except Exception as exc:
                logging.exception("PDF conversion failed")
                raise HTTPException(500, "Conversion failed. Check that the PDF is readable and try again.") from exc
    finally:
        await file.close()
