"""
RAG pipeline for AITA.
No LangChain — just openai + faiss directly.
"""

import os
import pickle
import re

import numpy as np
import faiss

from aita_core.config import get_config
from aita_core import providers

# Lazy-loaded state
_index = None
_chunks = None


def _load_index():
    global _index, _chunks
    if _index is None:
        cfg = get_config()
        _index = faiss.read_index(os.path.join(cfg.faiss_db_dir, "index.faiss"))
        with open(os.path.join(cfg.faiss_db_dir, "metadata.pkl"), "rb") as f:
            _chunks = pickle.load(f)


SCHEDULE_INSTRUCTION = """
CURRENT DATE AND SCHEDULE (authoritative — this is system-provided, not retrieved):
Today is {today}. The class is in instructional Week {current_week}.
This week's topic: {this_week}
Next class meeting: {next_class}.{meeting_pattern}

Full schedule:
{rows}

RULES FOR USING THIS:
- You DO know today's date, the current week, and the full course calendar. Never
  say you lack access to the schedule or syllabus, and never ask the student what
  week it is — you were just told.
- Answer "what are we doing this week / next class" directly from the table above.
- For deadlines, grading, exam logistics or submission rules NOT shown above and
  not present in the retrieved materials, say the syllabus did not surface that
  detail and point the student to the course page. Do not invent a policy or date.
"""


WEEK_CONTEXT_INSTRUCTION = """
IMPORTANT — WEEK-AWARE INSTRUCTION:
The class is currently in Week {current_week}.
{current_hw_line}
Topics covered so far: {covered_topics}

Topics NOT yet covered: {future_topics}

STRICT RULE — FUTURE LECTURE TOPICS:
If the student asks about a lecture topic that has NOT been covered yet, you MUST:
1. Say: "That's a great question! We'll cover that topic later in the course."
2. Give AT MOST a one-sentence definition — no formulas, no numbers, no calculations.
3. Do NOT provide specific values (like rates, speeds, constants) for future topics.
4. Redirect: "For now, let's focus on the current material. Is there anything about \
[current topic] I can help with?"
This is an absolute rule. Even if you know the answer, do NOT provide detailed \
information about future topics. Giving incorrect or premature information is worse \
than redirecting the student.
"""

HOMEWORK_POLICY_INSTRUCTION = """
HOMEWORK POLICY:
- Students ARE allowed to work ahead. If a student asks about a homework from any week, \
help them with its concepts normally.
- Each retrieved excerpt below is tagged with its source, e.g. "[Source: Homework: HW1.pdf]". \
Treat those tags as the source of truth for which assignment a passage belongs to.
- If the student names a problem WITHOUT saying which homework (e.g., "problem 2"), assume \
they mean {current_hw_ref}; if they name a specific homework/lab by number, use that one.
- CRITICAL — NEVER invent or guess what a problem asks. Only describe a specific problem's \
contents if that problem's text is actually present in the retrieved excerpts below AND the \
excerpt's source matches the homework/lab in question. If the problem is not in the excerpts, \
or the only excerpts are from a DIFFERENT homework or lab than the one asked about, do NOT \
summarize, paraphrase, or guess the problem. Instead tell the student you don't have that \
specific problem's text and ask them to paste it. Never answer a question about one assignment \
using a different assignment's problem (e.g., do not use HW2 or a Lab to describe a HW1 problem).
- You may always help with the underlying concepts and methods even when you lack the exact \
problem text — just don't fabricate what the assignment says.
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

NO_CONTEXT_WARNING_GENERIC = """
WARNING — NO COURSE MATERIALS RETRIEVED:
No course materials were found matching this query. Do NOT provide detailed answers \
from your own knowledge — they may be incorrect. Tell the student you don't have \
course materials on this topic and ask them to rephrase their question.
"""


def _resolve_current_hw(cfg, current_week):
    """The homework a student is most likely working on now.

    Assignments are keyed by the week they're DUE, so early in a week students are
    typically working on the next upcoming one (e.g. in week 1 they work on HW1,
    which is due week 2). Prefer an exact week match, then the next upcoming HW,
    then the most recent past one. Returns None if no HW schedule is configured.
    """
    week_to_hw = cfg.week_to_hw
    if not week_to_hw:
        return None
    if current_week in week_to_hw:
        return week_to_hw[current_week]
    upcoming = [w for w in week_to_hw if w >= current_week]
    if upcoming:
        return week_to_hw[min(upcoming)]
    past = [w for w in week_to_hw if w < current_week]
    if past:
        return week_to_hw[max(past)]
    return None



def build_schedule_block(cfg, current_week, today=None):
    """Date + week + full calendar. Independent of week_aware by design."""
    from datetime import date as _date, timedelta as _timedelta

    if not cfg.semester_start or not cfg.week_topics:
        return ""
    today = today or _date.today()
    start = _date.fromisoformat(cfg.semester_start)  # Monday of week 1

    rows = []
    for wk, topics in sorted(cfg.week_topics.items()):
        mon = start + _timedelta(days=7 * (wk - 1))
        mark = "  <-- CURRENT WEEK" if wk == current_week else ""
        rows.append(f"  Week {wk:>2} (week of {mon:%b %d}): {'; '.join(topics)}{mark}")

    mon = start + _timedelta(days=7 * (current_week - 1))
    upcoming = [mon + _timedelta(days=d) for d in range(7)
                if mon + _timedelta(days=d) >= today]
    next_class = f"{upcoming[0]:%A, %B %d}" if upcoming else f"{mon + _timedelta(days=7):%A, %B %d}"

    pattern = f" {cfg.meeting_pattern}" if cfg.meeting_pattern else ""
    return SCHEDULE_INSTRUCTION.format(
        today=f"{today:%A, %B %d, %Y}",
        current_week=current_week,
        this_week="; ".join(cfg.week_topics.get(current_week, ["-"])),
        next_class=next_class,
        meeting_pattern=pattern,
        rows="\n".join(rows),
    )


def build_system_prompt(current_week, has_context=True):
    """Build system prompt with week-awareness and exam scope."""
    cfg = get_config()

    current_hw = _resolve_current_hw(cfg, current_week) or "the most recent homework"

    current_hw_line = f"The current homework assignment is: {current_hw}"
    current_hw_ref = current_hw

    prompt = cfg.system_prompt

    # Week-gating (future-topic redirection) is optional per course.
    if cfg.week_aware:
        covered = cfg.get_topics_covered(current_week)
        future = cfg.get_topics_not_covered(current_week)
        prompt += "\n\n" + WEEK_CONTEXT_INSTRUCTION.format(
            current_week=current_week,
            covered_topics=", ".join(covered),
            future_topics=", ".join(future) if future else "None (all topics covered)",
            current_hw_line=current_hw_line,
        )

    prompt += "\n\n" + HOMEWORK_POLICY_INSTRUCTION.format(current_hw_ref=current_hw_ref)

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

    if getattr(cfg, "inject_schedule", False):
        try:
            block = build_schedule_block(cfg, current_week)
            if block:
                prompt += "\n\n" + block
        except Exception:
            pass  # never break a reply over the schedule block

    # Warn when no context was retrieved
    if not has_context:
        prompt += "\n\n" + (NO_CONTEXT_WARNING if cfg.week_aware else NO_CONTEXT_WARNING_GENERIC)

    return prompt


def retrieve(query, k=None, current_week=15):
    """Retrieve top-k relevant chunks, filtered to only topics covered by current_week."""
    _load_index()
    cfg = get_config()
    if k is None:
        k = cfg.retrieval_k

    qvec = providers.embed_texts(cfg, [query])
    faiss.normalize_L2(qvec)

    fetch_k = min(k * 4, _index.ntotal)
    scores, indices = _index.search(qvec, fetch_k)

    min_score = getattr(cfg, "retrieval_min_score", 0.0)
    eligible = []  # every chunk that passes score + week gating, best first
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        if min_score and float(score) < min_score:
            continue
        chunk_week = _chunks[idx]["metadata"].get("max_week", 1)
        source_label = _chunks[idx]["metadata"].get("source_label", "")
        # Homework content is always available (students can work ahead);
        # lecture/topic content is gated by current week only when week_aware.
        is_homework = "Homework" in source_label
        if cfg.week_aware and not is_homework and chunk_week > current_week:
            continue
        eligible.append((is_homework, {
            "text": _chunks[idx]["text"],
            "source": source_label,
            "file_path": _chunks[idx]["metadata"].get("source", ""),
            "score": float(score),
        }))
    return [c for _, c in _balance_sources(eligible, k, cfg)]


def _balance_sources(eligible, k, cfg):
    """Choose k chunks from ``eligible`` (best first) per cfg.retrieval_source_balance.

    A pasted problem statement is textually close to a homework problem statement,
    so an embedding model can rank homework above the handout that explains the
    method -- leaving the assistant with the question restated and nothing to teach
    from. These rules keep conceptual material in the context window.
    """
    rule = getattr(cfg, "retrieval_source_balance", "") or ""
    top = eligible[:k]
    if rule == "guarantee":
        # Only bites when EVERY selected chunk is homework: swap the weakest for
        # the best conceptual chunk still above threshold.
        if top and all(is_hw for is_hw, _ in top):
            extra = next((e for e in eligible[k:] if not e[0]), None)
            if extra is not None:
                top = top[:k - 1] + [extra]
        return top
    if rule == "cap":
        max_hw = getattr(cfg, "retrieval_max_homework", 2)
        out, n_hw = [], 0
        for is_hw, chunk in eligible:
            if is_hw:
                if n_hw >= max_hw:
                    continue
                n_hw += 1
            out.append((is_hw, chunk))
            if len(out) == k:
                break
        return out
    return top


def build_messages(chat_history, user_query, context_chunks, current_week):
    """Build the OpenAI-style message list (converted per-provider downstream)."""
    # Tag each excerpt with its source so the model can tell which assignment a
    # passage belongs to (and refuse to answer from a mismatched homework/lab).
    context = "\n\n---\n\n".join(
        (f"[Source: {c['source']}]\n{c['text']}" if c.get("source") else c["text"])
        for c in context_chunks
    )
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

    current_hw = _resolve_current_hw(cfg, current_week)
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
    Returns (assistant_message, sources, messages). ``messages`` is the exact
    prompt that was sent, so a shadow model can be given the identical input.
    """
    cfg = get_config()
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
    assistant_message = providers.chat_complete(cfg, messages)
    return assistant_message, sources, messages
