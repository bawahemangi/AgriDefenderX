"""
Generation half of the advisory RAG pipeline.

Design intent (matches the problem statement's ask for reliable, locally
relevant advisories, and the general rule "don't let an LLM invent
agricultural treatments"): the LLM is NEVER the source of factual
agronomic content. It only rephrases/translates content that was already
retrieved verbatim from the curated knowledge_base/ markdown files. If
retrieval finds nothing relevant (low similarity), we say so and route to
expert referral rather than letting a model improvise.

Two modes:
    - TEMPLATE mode (default, always available, zero external calls):
      directly extracts the relevant sections from the retrieved markdown
      into a clean farmer-facing summary. No API key needed.
    - LLM mode (if ANTHROPIC_API_KEY is set): additionally asks Claude to
      (a) tighten the template output into a warmer, more farmer-friendly
      tone personalized with crop/growth-stage/risk context, and
      (b) translate the result into the requested language. The prompt
      explicitly restricts the model to the provided context only.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from retriever import RetrievedDoc, build_query, get_retriever

SUPPORTED_LANGUAGES = {"en": "English", "mr": "Marathi", "hi": "Hindi"}

# Module-level cache: (original_text, language) → translated_text.
# Prevents re-hitting Google Translate for the same advisory text within a process.
_translation_cache: dict[tuple[str, str], str] = {}


@dataclass
class Advisory:
    disease_title: str
    risk_band: str | None
    actions: list[str]
    safe_input_use: str
    referral_note: str
    sources: list[str]
    language: str = "en"
    text: str = ""
    generation_mode: str = "template"


def _extract_section(markdown: str, header: str) -> str:
    pattern = rf"##\s*{re.escape(header)}\s*\n(.*?)(?=\n##|\Z)"
    match = re.search(pattern, markdown, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _bullets(section_text: str) -> list[str]:
    return [line.lstrip("- ").strip() for line in section_text.splitlines()
            if line.strip().startswith("-")]


def _compile_template(doc: RetrievedDoc, risk_band: str | None) -> Advisory:
    actions = _bullets(_extract_section(doc.content, "Integrated pest & disease management actions")) \
        or _bullets(_extract_section(doc.content, "Integrated pest management actions")) \
        or _bullets(_extract_section(doc.content, "Recommended actions"))
    safe_use = _extract_section(doc.content, "Safe input use")
    referral = _extract_section(doc.content, "When to refer to an expert or lab")
    monitoring = _extract_section(doc.content, "Follow-up monitoring")

    lines = [f"**{doc.title}**", ""]
    if risk_band:
        lines.append(f"Current risk level for your field: **{risk_band}**")
        lines.append("")
    if actions:
        lines.append("Recommended actions:")
        lines.extend(f"- {a}" for a in actions)
        lines.append("")
    if safe_use:
        lines.append(f"Safe input use: {safe_use}")
        lines.append("")
    if referral:
        lines.append(f"When to get expert help: {referral}")
        lines.append("")
    if monitoring:
        lines.append(f"Follow-up: {monitoring}")

    return Advisory(
        disease_title=doc.title,
        risk_band=risk_band,
        actions=actions,
        safe_input_use=safe_use,
        referral_note=referral,
        sources=[doc.filename],
        text="\n".join(lines).strip(),
        generation_mode="template",
    )


def _call_claude(prompt: str) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import requests
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    except Exception:
        return None


def _llm_polish_and_translate(advisory: Advisory, language: str, crop: str, growth_stage: str) -> Advisory:
    lang_name = SUPPORTED_LANGUAGES.get(language, "English")
    prompt = (
        "You are formatting an agricultural advisory for a farmer. "
        "Use ONLY the facts in the CONTENT below -- do not add any new "
        "recommendations, dosages, or facts that are not present in it. "
        "Make it warm, clear, and easy to act on for a farmer, organized "
        "with short sections. "
        f"Then translate the final result fully into {lang_name}. "
        f"Context: crop={crop}, growth stage={growth_stage}, "
        f"risk level={advisory.risk_band}.\n\n"
        f"CONTENT:\n{advisory.text}\n\n"
        f"Return only the final {lang_name} advisory text, no preamble."
    )
    result = _call_claude(prompt)
    if result:
        advisory.text = result
        advisory.language = language
        advisory.generation_mode = "llm_grounded"
    return advisory


def _translate_fallback(advisory: Advisory, language: str) -> Advisory:
    """
    Translate advisory text using deep-translator.

    Strategy (in order):
      1. MyMemory (primary) — free, no per-second rate limit, no API key.
         Text is split into ≤450-char sentence chunks and translated
         sequentially (MyMemory serialises concurrent requests from the
         same IP, so parallelism doesn't help here).
      2. GoogleTranslator (backup) — free but rate-limited to 5 req/s;
         uses translate_batch (one HTTP call for all chunks) with
         exponential back-off.
      Both share the module-level _translation_cache so the same advisory
      text is never re-sent within a process lifetime.
      NOTE: This function is called from a background daemon thread in
      scan_views.py — callers should never block on it directly.
    """
    import time

    _MYMEMORY_LANG = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-US"}
    _MM_CHUNK = 450   # MyMemory hard limit ~500 chars

    cache_key = (advisory.text, language)
    cached = _translation_cache.get(cache_key)
    if cached is not None:
        advisory.text, advisory.language = cached["text"], language
        advisory.generation_mode = cached["mode"]
        return advisory

    def _split_sentences(text: str, limit: int) -> list[str]:
        """Accumulate sentences into chunks of ≤limit chars."""
        sentences, chunks, current = [], [], ""
        for line in text.splitlines(keepends=True):
            parts = line.replace(". ", ".|").replace("? ", "?|").replace("! ", "!|").split("|")
            sentences.extend(parts)
        for s in sentences:
            if len(current) + len(s) > limit:
                if current:
                    chunks.append(current.rstrip())
                current = s
            else:
                current += s
        if current:
            chunks.append(current.rstrip())
        return chunks or [text]

    translated_text: str | None = None
    mode = "template"

    # ── Try 1: MyMemory (sequential — parallel doesn't help) ─────────────
    try:
        from deep_translator import MyMemoryTranslator
        mm_lang = _MYMEMORY_LANG.get(language, f"{language}-IN")
        chunks = _split_sentences(advisory.text, _MM_CHUNK)
        translator = MyMemoryTranslator(source="en-US", target=mm_lang)
        parts = [translator.translate(c) or c for c in chunks]
        translated_text = "".join(parts)
        mode = "mymemory_translated"

    except Exception as exc:
        print(f"[advisory] MyMemory failed ({type(exc).__name__}: {exc}), "
              "trying Google Translate…")

    # ── Try 2: GoogleTranslator backup (with exponential backoff) ────────
    if not translated_text:
        try:
            from deep_translator import GoogleTranslator
            g_chunks = _split_sentences(advisory.text, 4500)
            translator = GoogleTranslator(source="en", target=language)
            for attempt in range(3):
                try:
                    results = translator.translate_batch(g_chunks)
                    translated_text = "\n\n".join(r or c for r, c in zip(results, g_chunks))
                    mode = "google_translated"
                    break
                except Exception as exc2:
                    if attempt == 2:
                        raise
                    wait = (2 ** attempt)
                    print(f"[advisory] Google attempt {attempt+1} failed, "
                          f"retrying in {wait}s…")
                    time.sleep(wait)
        except Exception as exc:
            print(f"[advisory] Translation to '{language}' failed entirely "
                  f"({type(exc).__name__}: {exc}). Showing English.")

    if translated_text:
        _translation_cache[cache_key] = {"text": translated_text, "mode": mode}
        advisory.text = translated_text
        advisory.language = language
        advisory.generation_mode = mode

    return advisory



def generate_advisory(
    crop: str,
    disease: str,
    growth_stage: str = "",
    risk_band: str | None = None,
    language: str = "en",
    low_confidence: bool = False,
) -> Advisory:
    retriever = get_retriever()
    query = build_query(crop, disease, growth_stage)
    hits = retriever.retrieve(query, top_k=1)

    if not hits:
        return Advisory(
            disease_title=disease,
            risk_band=risk_band,
            actions=[],
            safe_input_use="",
            referral_note="No matching guidance found in the knowledge base for this case.",
            sources=[],
            language=language,
            text=(
                "We could not find verified guidance for this specific case in our "
                "knowledge base. Please contact your local agriculture extension "
                "officer for an in-person assessment rather than guessing at treatment."
            ),
            generation_mode="no_match_fallback",
        )

    advisory = _compile_template(hits[0], risk_band)

    if low_confidence:
        advisory.text += (
            "\n\n**Note:** The image analysis confidence for this diagnosis was low. "
            "Treat this as a preliminary suggestion, not a confirmed diagnosis -- "
            "please get expert or lab confirmation before large-scale treatment."
        )

    if language != "en":
        advisory = _llm_polish_and_translate(advisory, language, crop, growth_stage)
        if advisory.generation_mode != "llm_grounded":
            advisory = _translate_fallback(advisory, language)
        
        if advisory.language != language:
            advisory.text += (
                f"\n\n[{SUPPORTED_LANGUAGES.get(language, language)} translation "
                f"unavailable -- set ANTHROPIC_API_KEY to enable live translation. "
                f"Showing English guidance above.]"
            )

    return advisory


if __name__ == "__main__":
    adv = generate_advisory(
        crop="Tomato", disease="Early blight", growth_stage="flowering",
        risk_band="HIGH", language="en", low_confidence=False,
    )
    print(f"[mode={adv.generation_mode}, sources={adv.sources}]\n")
    print(adv.text)
