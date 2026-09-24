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
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='en', target=language)
        result = translator.translate(advisory.text)
        if result:
            advisory.text = result
            advisory.language = language
            advisory.generation_mode = "deep_translated"
    except Exception as e:
        print(f"Translation fallback failed: {e}")
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
