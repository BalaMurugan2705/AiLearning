import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from pydantic import BaseModel

from rag.config import DOCUMENTS_DIR, GROQ_API_KEY, SUPPORTED_EXTENSIONS, TOP_K
from rag.pipeline import RAGPipeline

app = FastAPI(title="RAG App")
templates = Jinja2Templates(directory="templates")
pipeline = RAGPipeline()


class AskRequest(BaseModel):
    question: str
    k: int = TOP_K


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"document_count": pipeline.document_count()}
    )


@app.get("/api/status")
async def status():
    return {"chunks_indexed": pipeline.document_count(), "configured": bool(GROQ_API_KEY)}


@app.post("/api/ingest")
async def ingest(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    Path(DOCUMENTS_DIR).mkdir(parents=True, exist_ok=True)
    dest = Path(DOCUMENTS_DIR) / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Uploads are additive. Wiping the index on every upload would make it
    # impossible to hold more than one document version at a time, which is
    # exactly what the sdk_version filter exists to disambiguate. Re-ingesting
    # the same path still replaces that file's own chunks.
    result = pipeline.ingest_path(str(dest))
    return {**result, "chunks_indexed_total": pipeline.document_count()}


@app.post("/api/ask")
async def ask(payload: AskRequest):
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured on the server.")
    if pipeline.document_count() == 0:
        raise HTTPException(status_code=400, detail="No documents indexed yet. Upload one first.")

    return pipeline.ask(payload.question, k=payload.k)


if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    uvicorn.run("app:app", host=args.host, port=args.port, reload=True)
