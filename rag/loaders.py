from pathlib import Path

from pypdf import PdfReader

from rag.config import SUPPORTED_EXTENSIONS


def load_document(path: Path) -> str:
    """Read a single document's text content based on its extension."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported file type: {suffix}")


def _load_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def iter_documents(path: Path):
    """Yield (file_path, text) for every supported document under path.

    If path is a single file, yields just that file (if supported).
    If path is a directory, walks it recursively.
    """
    if path.is_file():
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path, load_document(path)
        return

    for file_path in sorted(path.rglob("*")):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            text = load_document(file_path)
            if text.strip():
                yield file_path, text
