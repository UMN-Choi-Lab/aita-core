"""
Shared document ingestion utilities for AITA.

Course-specific repos use these functions in their own add_document.py,
providing their own collect_*() functions for course material layouts.

Usage in a course repo's add_document.py:

    from aita_core.ingest import (
        get_week_for_filename, load_pdf, load_tex,
        chunk_documents, get_embeddings, build_faiss_index, save_index,
    )
    from config import CONFIG

    # Define your own collect_handouts(), collect_homework_questions(), etc.
    # Then call the shared pipeline:
    chunks = chunk_documents(all_docs)
    embeddings = get_embeddings(chunks, CONFIG)
    index = build_faiss_index(embeddings)
    save_index(index, chunks, CONFIG.faiss_db_dir, CONFIG.docs_dir, CONFIG.backup_dir)
"""

import os
import re
import pickle
import shutil
import datetime

import numpy as np
import faiss
from openai import OpenAI
from pdfminer.high_level import extract_text

from aita_core.utils import save_docs_to_jsonl


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


# ---------------------------------------------------------------------------
# Week tagging
# ---------------------------------------------------------------------------

def get_week_for_filename(filename, topic_num_to_week, hw_num_to_week,
                          lab_num_to_week, study_guide_to_week):
    """Determine which week a document belongs to based on its filename."""
    match = re.match(r"^(\d+)\s", filename)
    if match:
        topic_num = int(match.group(1))
        return topic_num_to_week.get(topic_num, 15)

    match = re.match(r"^HW(\d+)", filename)
    if match:
        hw_num = int(match.group(1))
        return hw_num_to_week.get(hw_num, 15)

    match = re.match(r"^Lab\s*(\d+)", filename)
    if match:
        lab_num = int(match.group(1))
        return lab_num_to_week.get(lab_num, 15)

    for guide_key, week in sorted(study_guide_to_week.items(), key=lambda x: -len(x[0])):
        if filename.startswith(guide_key):
            return week

    if "syllabus" in filename.lower():
        return 1

    return 1


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def clean_pdf_text(text):
    text = text.replace("\x0c", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def load_pdf(file_path, source_label, max_week=1):
    text = extract_text(file_path)
    text = clean_pdf_text(text)
    if not text:
        return []
    return [{"text": text, "metadata": {"source": file_path, "source_label": source_label, "max_week": max_week}}]


def load_tex(file_path, source_label, max_week=1):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    content = re.sub(r"(?m)^%.*$", "", content)
    content = re.sub(
        r"\\(documentclass|usepackage|begin\{document\}|end\{document\}|maketitle|input\{[^}]*\}|newcommand[^}]*\}[^}]*\})",
        "", content,
    )
    content = content.strip()
    if not content:
        return []
    return [{"text": content, "metadata": {"source": file_path, "source_label": source_label, "max_week": max_week}}]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text, chunk_size=2048, overlap=256):
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def chunk_documents(docs, chunk_size=2048, overlap=256):
    """Split all documents into chunks, preserving metadata."""
    all_chunks = []
    for doc in docs:
        text_chunks = chunk_text(doc["text"], chunk_size, overlap)
        for chunk in text_chunks:
            label = doc["metadata"]["source_label"]
            all_chunks.append({
                "text": f"Source: {label}\n{chunk}",
                "metadata": doc["metadata"],
            })
    return all_chunks


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def get_embeddings(texts, embedding_model="text-embedding-3-large", batch_size=100):
    """Call OpenAI embeddings API in batches. Returns numpy array."""
    client = _get_client()
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"  Embedding batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1} ({len(batch)} chunks)")
        response = client.embeddings.create(model=embedding_model, input=batch)
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
    return np.array(all_embeddings, dtype="float32")


# ---------------------------------------------------------------------------
# FAISS index management
# ---------------------------------------------------------------------------

def build_faiss_index(embeddings):
    """Build a FAISS index from embeddings."""
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)
    return index


def save_index(index, chunks, faiss_dir, docs_dir, backup_dir):
    """Save FAISS index and chunk metadata, with backup of existing data."""
    os.makedirs(faiss_dir, exist_ok=True)
    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)

    index_path = os.path.join(faiss_dir, "index.faiss")
    meta_path = os.path.join(faiss_dir, "metadata.pkl")
    doc_jsonl = os.path.join(docs_dir, "doc.jsonl")
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")

    if os.path.exists(index_path):
        print("Existing index found. Backing up...")
        bak = os.path.join(backup_dir, timestamp)
        os.makedirs(bak, exist_ok=True)
        shutil.copy2(index_path, os.path.join(bak, "index.faiss"))
        if os.path.exists(meta_path):
            shutil.copy2(meta_path, os.path.join(bak, "metadata.pkl"))
        if os.path.exists(doc_jsonl):
            shutil.copy2(doc_jsonl, os.path.join(bak, "doc.jsonl"))

    faiss.write_index(index, index_path)

    with open(meta_path, "wb") as f:
        pickle.dump(chunks, f)

    save_docs_to_jsonl(chunks, doc_jsonl)

    print(f"Index saved to {faiss_dir} ({index.ntotal} vectors)")
    print(f"Document records saved to {doc_jsonl}")


# ---------------------------------------------------------------------------
# Syllabus collector (common across courses)
# ---------------------------------------------------------------------------

def collect_syllabus(course_materials_dir):
    """Load syllabus from standard location."""
    docs = []
    tex_path = os.path.join(course_materials_dir, "syllabus", "Syllabus.tex")
    pdf_path = os.path.join(course_materials_dir, "syllabus", "Syllabus.pdf")
    if os.path.exists(tex_path):
        print("  Loading Syllabus (LaTeX, week 1)")
        docs.extend(load_tex(tex_path, "Syllabus", max_week=1))
    elif os.path.exists(pdf_path):
        print("  Loading Syllabus (PDF, week 1)")
        docs.extend(load_pdf(pdf_path, "Syllabus", max_week=1))
    return docs
