"""
RAG pipeline for AITA.
No LangChain — just openai + faiss directly.
"""

import os
import pickle

import numpy as np
import faiss
from openai import OpenAI

from aita_core.config import get_config

# Lazy-loaded state
_client = None
_index = None
_chunks = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def _load_index():
    global _index, _chunks
    if _index is None:
        cfg = get_config()
        _index = faiss.read_index(os.path.join(cfg.faiss_db_dir, "index.faiss"))
        with open(os.path.join(cfg.faiss_db_dir, "metadata.pkl"), "rb") as f:
            _chunks = pickle.load(f)


FUTURE_TOPIC_INSTRUCTION = """
IMPORTANT — WEEK-AWARE INSTRUCTION:
The class is currently in Week {current_week}.
{current_hw_line}
Topics covered so far: {covered_topics}

Topics NOT yet covered: {future_topics}

If the student asks about a topic that has NOT been covered yet:
- Tell them: "Great question! We'll cover that topic later in the course."
- Give a brief, high-level overview (1-2 sentences max) so they have some context
- Do NOT go into detail, formulas, derivations, or worked examples for future topics
- Redirect them to focus on the current material

If the student asks about "this week's homework" or "the current homework", refer to {current_hw_ref}.
If the student says "problem 1" or "problem 2" etc. without specifying which homework, \
assume they mean {current_hw_ref} and use the retrieved context from that homework.
"""


def build_system_prompt(current_week):
    """Build system prompt with week-awareness."""
    cfg = get_config()
    covered = cfg.get_topics_covered(current_week)
    future = cfg.get_topics_not_covered(current_week)

    week_to_hw = cfg.week_to_hw
    current_hw = week_to_hw.get(current_week, None)
    if not current_hw:
        for w in range(current_week, 0, -1):
            if w in week_to_hw:
                current_hw = week_to_hw[w]
                break
    current_hw = current_hw or "the most recent homework"

    current_hw_line = f"The current homework assignment is: {current_hw}"
    current_hw_ref = current_hw

    prompt = cfg.system_prompt
    prompt += "\n\n" + FUTURE_TOPIC_INSTRUCTION.format(
        current_week=current_week,
        covered_topics=", ".join(covered),
        future_topics=", ".join(future) if future else "None (all topics covered)",
        current_hw_line=current_hw_line,
        current_hw_ref=current_hw_ref,
    )
    return prompt


def retrieve(query, k=None, current_week=15):
    """Retrieve top-k relevant chunks, filtered to only topics covered by current_week."""
    _load_index()
    cfg = get_config()
    client = _get_client()
    if k is None:
        k = cfg.retrieval_k

    resp = client.embeddings.create(model=cfg.embedding_model, input=[query])
    qvec = np.array([resp.data[0].embedding], dtype="float32")
    faiss.normalize_L2(qvec)

    fetch_k = min(k * 4, _index.ntotal)
    scores, indices = _index.search(qvec, fetch_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        chunk_week = _chunks[idx]["metadata"].get("max_week", 1)
        if chunk_week > current_week:
            continue
        results.append({
            "text": _chunks[idx]["text"],
            "source": _chunks[idx]["metadata"]["source_label"],
            "file_path": _chunks[idx]["metadata"].get("source", ""),
            "score": float(score),
        })
        if len(results) >= k:
            break
    return results


def build_messages(chat_history, user_query, context_chunks, current_week):
    """Build the message list for the OpenAI chat completion."""
    context = "\n\n---\n\n".join(c["text"] for c in context_chunks)
    system_prompt = build_system_prompt(current_week)

    messages = [
        {"role": "system", "content": system_prompt + f"\n\nRetrieved course materials:\n{context}"},
    ]

    for msg in chat_history[-20:]:
        messages.append(msg)

    messages.append({"role": "user", "content": user_query})

    return messages


def _inject_current_hw(query, context_chunks, current_week):
    """If the query mentions homework, ensure the current HW is in retrieved chunks."""
    _load_index()
    cfg = get_config()
    hw_keywords = ["homework", "hw", "assignment", "this week's hw", "current hw"]
    if not any(kw in query.lower() for kw in hw_keywords):
        return context_chunks

    week_to_hw = cfg.week_to_hw
    current_hw = week_to_hw.get(current_week)
    if not current_hw:
        for w in range(current_week, 0, -1):
            if w in week_to_hw:
                current_hw = week_to_hw[w]
                break
    if not current_hw:
        return context_chunks

    # Check if current HW is already in results
    hw_label = f"Homework: {current_hw}.pdf"
    if any(hw_label in c.get("source", "") for c in context_chunks):
        return context_chunks

    # Find and inject the first chunk from the current HW
    for i, chunk in enumerate(_chunks):
        label = chunk["metadata"].get("source_label", "")
        if current_hw in label and "Homework" in label:
            chunk_week = chunk["metadata"].get("max_week", 1)
            if chunk_week <= current_week:
                context_chunks.insert(0, {
                    "text": chunk["text"],
                    "source": label,
                    "file_path": chunk["metadata"].get("source", ""),
                    "score": 1.0,
                })
                break
    return context_chunks


def chat(user_query, chat_history=None, current_week=15):
    """
    Full RAG pipeline: retrieve context, build prompt, generate response.
    Returns (assistant_message, sources).
    """
    cfg = get_config()
    client = _get_client()
    if chat_history is None:
        chat_history = []

    context_chunks = retrieve(user_query, current_week=current_week)
    context_chunks = _inject_current_hw(user_query, context_chunks, current_week)

    seen = set()
    sources = []
    for c in context_chunks:
        if c["source"] not in seen:
            seen.add(c["source"])
            sources.append({"label": c["source"], "file_path": c["file_path"]})

    messages = build_messages(chat_history, user_query, context_chunks, current_week)
    response = client.chat.completions.create(
        model=cfg.llm_model,
        messages=messages,
        temperature=cfg.llm_temperature,
    )

    assistant_message = response.choices[0].message.content
    return assistant_message, sources
