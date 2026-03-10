"""
RAG pipeline for AITA.
No LangChain — just openai + faiss directly.
"""

import os
import pickle
import re

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

STRICT RULE — FUTURE TOPICS:
If the student asks about a topic that has NOT been covered yet, you MUST:
1. Say: "That's a great question! We'll cover that topic later in the course."
2. Give AT MOST a one-sentence definition — no formulas, no numbers, no calculations.
3. Do NOT provide specific values (like rates, speeds, constants) for future topics.
4. Redirect: "For now, let's focus on the current material. Is there anything about \
[current topic] I can help with?"
This is an absolute rule. Even if you know the answer, do NOT provide detailed \
information about future topics. Giving incorrect or premature information is worse \
than redirecting the student.

If the student asks about "this week's homework" or "the current homework", refer to {current_hw_ref}.
If the student says "problem 1" or "problem 2" etc. without specifying which homework, \
assume they mean {current_hw_ref} and use the retrieved context from that homework.
"""

EXAM_SCOPE_INSTRUCTION = """
EXAM SCOPE INFORMATION:
{exam_scope_text}

CRITICAL RULE — EXAM STUDY GUIDES:
When a student asks about preparing for a specific exam (e.g., "study guide for midterm 2", \
"practice exam", "what's on the midterm"), you MUST:
- ONLY include topics that fall within that exam's scope as listed above.
- Do NOT include topics from weeks beyond the exam's week range.
- Base your study guide on the retrieved course materials, not your own knowledge.
- If you are unsure which exam they mean, ask them to clarify.
"""

NO_CONTEXT_WARNING = """
WARNING — NO COURSE MATERIALS RETRIEVED:
No course materials were found matching this query. This likely means the topic has not \
been covered yet, or the query does not match any course content.
You MUST NOT provide detailed answers from your own knowledge — they may be incorrect.
Instead, check if the topic appears in the "NOT yet covered" list above and redirect \
accordingly. If unsure, tell the student: "I don't have course materials on this topic \
yet. Could you rephrase your question, or is this a topic we haven't covered?"
"""


def build_system_prompt(current_week, has_context=True):
    """Build system prompt with week-awareness and exam scope."""
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

    # Add exam scope if configured
    if cfg.exam_scope:
        lines = []
        for exam_name, scope in sorted(cfg.exam_scope.items()):
            topics = cfg.get_exam_topics(exam_name)
            if topics:
                lines.append(
                    f"- {exam_name} (weeks {scope['week_start']}-{scope['week_end']}): "
                    f"{', '.join(topics)}"
                )
        if lines:
            prompt += "\n\n" + EXAM_SCOPE_INSTRUCTION.format(
                exam_scope_text="\n".join(lines),
            )

    # Warn when no context was retrieved
    if not has_context:
        prompt += "\n\n" + NO_CONTEXT_WARNING

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
    system_prompt = build_system_prompt(
        current_week, has_context=bool(context_chunks),
    )

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


def _identify_exam(query_lower, cfg):
    """Identify which exam the student is asking about from the query text."""
    if not cfg.exam_scope:
        return None

    # Try exact name matches first (e.g., "midterm 1", "midterm 2", "final")
    for exam_name in sorted(cfg.exam_scope.keys()):
        name_lower = exam_name.lower()
        if name_lower in query_lower:
            return exam_name
        # Handle "midterm exam 2" matching "Midterm 2"
        parts = name_lower.split()
        if len(parts) >= 2 and all(p in query_lower for p in parts):
            return exam_name

    # Match "final" keyword
    if "final" in query_lower:
        for name in cfg.exam_scope:
            if "final" in name.lower():
                return name

    # Match generic "midterm" — pick the most relevant one
    if "midterm" in query_lower:
        # Check for a number in the query
        match = re.search(r"midterm\s*(?:exam\s*)?(\d+)", query_lower)
        if match:
            target = f"Midterm {match.group(1)}"
            if target in cfg.exam_scope:
                return target

        # No number — return the latest midterm (students usually ask about upcoming)
        midterms = sorted(
            [(n, s) for n, s in cfg.exam_scope.items() if "midterm" in n.lower()],
            key=lambda x: x[1].get("week_end", 0),
        )
        if midterms:
            return midterms[-1][0]

    return None


def _inject_exam_review(query, context_chunks, current_week):
    """For exam-related queries, retrieve topic-relevant content using exam scope."""
    cfg = get_config()
    if not cfg.exam_scope:
        return context_chunks

    exam_keywords = [
        "midterm", "study guide", "review for", "practice exam",
        "final exam", "prepare for exam", "what's on the exam",
        "what will be on", "exam review",
    ]
    query_lower = query.lower()
    if not any(kw in query_lower for kw in exam_keywords):
        return context_chunks

    target_exam = _identify_exam(query_lower, cfg)
    if not target_exam:
        return context_chunks

    topics = cfg.get_exam_topics(target_exam)
    if not topics:
        return context_chunks

    # Retrieve chunks using exam topics as a synthetic query
    topic_query = f"Key concepts for exam review: {', '.join(topics)}"
    topic_results = retrieve(topic_query, k=cfg.retrieval_k, current_week=current_week)

    # Merge: add new unique sources from topic retrieval
    existing_sources = {c["source"] for c in context_chunks}
    for chunk in topic_results:
        if chunk["source"] not in existing_sources:
            context_chunks.append(chunk)
            existing_sources.add(chunk["source"])

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
    context_chunks = _inject_exam_review(user_query, context_chunks, current_week)

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
