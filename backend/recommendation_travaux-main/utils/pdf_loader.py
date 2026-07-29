import os
from pypdf import PdfReader


def load_text(filepath: str) -> str:
    """Extrait le texte brut d'un PDF ou d'un fichier texte."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        reader = PdfReader(filepath)
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n".join(pages)
    elif ext in (".txt", ".md"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        raise ValueError(f"Format non supporte: {ext}")


def chunk_text(text: str, chunk_size: int, overlap: int):
    """Decoupe un texte long en morceaux avec chevauchement."""
    chunks = []
    start = 0
    n = len(text)
    if n == 0:
        return chunks
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = end - overlap
    return chunks


def list_documents(documents_dir: str):
    """Liste les documents supportes dans le dossier documents/."""
    exts = (".pdf", ".txt", ".md")
    if not os.path.isdir(documents_dir):
        return []
    return sorted(
        os.path.join(documents_dir, f)
        for f in os.listdir(documents_dir)
        if f.lower().endswith(exts)
    )
