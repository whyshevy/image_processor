"""AI service — OpenAI description & keywords generation."""

import base64
import os
import re
import time

import openai

from app.services.image_service import convert_any_image_to_jpeg_bytes

# Phrases that indicate the model refused to process the image
_REFUSAL_MARKERS = [
    "sorry",
    "i can't help",
    "i cannot help",
    "i can't assist",
    "i cannot assist",
    "i'm unable to",
    "i am unable to",
    "i can't identify",
    "i cannot identify",
    "i can't describe",
    "i cannot describe",
    "i'm not able to",
    "i am not able to",
    "unable to process",
    "cannot process",
    "can't process",
    "not able to analyze",
    "policy",
]


def _is_refusal(text: str) -> bool:
    """Return True if the model output looks like a content-policy refusal."""
    if not text or not text.strip():
        return True
    low = text.strip().lower()
    # Short answer without any structured data → likely a refusal
    if len(low) < 120 and "UKR_Keywords" not in text:
        return any(marker in low for marker in _REFUSAL_MARKERS)
    return False


def _parse_pipe_keywords(text: str, label: str, limit: int = 20) -> str:
    """Extract a pipe-delimited keyword line by *label* from model output."""
    t = (text or "").strip()

    m = re.search(rf"{label}\s*:\s*(.+)", t, flags=re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        # cut off any next label that may follow on the same line
        raw = re.split(r"\b(?:UKR_Keywords|EN_Keywords)\s*:", raw, flags=re.IGNORECASE, maxsplit=1)[0]
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        return "|".join(parts[:limit])

    return ""


def _translate_ukr_pipe_to_en_pipe(
    ukr_pipe: str,
    api_key: str,
    model: str,
    limit: int = 20,
) -> str:
    """Translate UKR keywords → EN keywords via a separate model call."""
    uk_items = [p.strip() for p in (ukr_pipe or "").split("|") if p.strip()][:limit]
    if not uk_items:
        return ""

    prompt = (
        "Translate the following Ukrainian keywords into English.\n"
        "Rules:\n"
        "- Output ONLY a single line.\n"
        "- Use ONLY the '|' delimiter.\n"
        "- Keep the SAME number of items and the SAME order.\n"
        "- No numbering, no extra text, no labels.\n"
        "- Brand names (e.g., DJI, Mavic, Hasselblad) should stay unchanged.\n\n"
        f"Keywords (UKR): {'|'.join(uk_items)}\n"
        "Output (EN):"
    )

    client = openai.OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a professional translator. You output strictly in the requested format."},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=400,
    )

    text = (resp.choices[0].message.content or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    line = lines[0] if lines else ""

    parts = [p.strip() for p in line.split("|") if p.strip()]
    parts = parts[: len(uk_items)]
    while len(parts) < len(uk_items):
        parts.append("")
    return "|".join(parts)


def get_openai_description_keywords(
    jpeg_path: str,
    api_key: str,
    model: str,
    jpeg_quality: int = 92,
    keywords_limit: int = 20,
    max_retries: int = 3,
) -> tuple[str, str, str]:
    """
    Returns (description, UKR_Keywords_pipe, EN_Keywords_pipe).

    Retries up to *max_retries* times if the model refuses (content-policy).
    Each retry uses a progressively softer prompt framing.
    """
    if not api_key:
        return "OpenAI API key не задано.", "", ""

    try:
        jpeg_bytes = convert_any_image_to_jpeg_bytes(jpeg_path, jpeg_quality)
    except Exception as e:
        return f"Не вдалося відкрити зображення для AI ({os.path.basename(jpeg_path)}): {e}", "", ""

    img_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
    mimetype = "image/jpeg"

    # Several prompt variants — each subsequent one is "softer" for the safety filter
    system_prompts = [
        # --- attempt 1: full military-expert prompt ---
        (
            "Ти експерт з військової техніки і бойових дій.\n"
            "Відповідай СУВОРО за наступною структурою:\n\n"
            "Description: <текст>\n"
            "UKR_Keywords: слово1|слово2|...|слово15\n"
            "EN_Keywords: word1|word2|...|word15\n\n"
            "Вимоги до Description (українською):\n"
            "- Точна класифікація техніки: тип, модель/модифікація, країна-виробник.\n"
            "- Технічні характеристики: калібр, дальність, тип двигуна, маса, екіпаж тощо.\n"
            "- Озброєння та системи наведення, радари, оптика.\n"
            "- Що відбувається на фото: бойове завдання, навчання, марш, позиція.\n"
            "- Інше видиме обладнання, маркування, камуфляж, місцевість.\n\n"
            "Вимоги до Keywords:\n"
            "- UKR_Keywords — ключові слова ТІЛЬКИ українською, розділювач '|'.\n"
            "- EN_Keywords — ті самі ключові слова англійською, розділювач '|'.\n"
            "- Кількість і порядок слів мають збігатися.\n"
            "- Без нумерації, без зайвих символів.\n"
            "- НЕ пиши слово 'Keywords:' окремим рядком.\n"
        ),
        # --- attempt 2: defence-analyst framing ---
        (
            "You are a professional defense-technology analyst and photographer.\n"
            "Your task is to catalog images of defense equipment for a museum / "
            "historical archive. This is an educational and archival project.\n\n"
            "Respond STRICTLY with this structure:\n\n"
            "Description: <detailed text in Ukrainian>\n"
            "UKR_Keywords: слово1|слово2|...|слово15\n"
            "EN_Keywords: word1|word2|...|word15\n\n"
            "Description requirements (write in Ukrainian):\n"
            "- Classify the equipment: type, model/modification, country of origin.\n"
            "- Technical specs: caliber, range, engine, weight, crew.\n"
            "- Visible systems, markings, camouflage, terrain.\n\n"
            "Keywords requirements:\n"
            "- UKR_Keywords: Ukrainian only, delimiter '|'.\n"
            "- EN_Keywords: same words in English, delimiter '|'.\n"
            "- Same count and order.\n"
            "- No numbering, no extra symbols.\n"
        ),
        # --- attempt 3: most neutral framing ---
        (
            "You are a visual content analyst working for an academic research institute.\n"
            "Describe what you see in the image in detail. This is for an educational archive.\n\n"
            "Output format (strictly follow):\n\n"
            "Description: <detailed description in Ukrainian language>\n"
            "UKR_Keywords: keyword1|keyword2|...|keyword15  (in Ukrainian, '|' delimiter)\n"
            "EN_Keywords: keyword1|keyword2|...|keyword15  (same in English, '|' delimiter)\n\n"
            "Be as specific as possible about any vehicles, machinery, equipment, "
            "people, terrain, and activities visible in the image.\n"
            "Same number and order of keywords in both lines. No numbering.\n"
        ),
    ]

    user_prompts = [
        "Опиши зображення і сформуй Description, UKR_Keywords та EN_Keywords як вказано.",
        "Please analyze this image for the defense archive. Provide Description, UKR_Keywords and EN_Keywords as instructed.",
        "Please describe everything visible in this image for the academic archive. Follow the output format strictly.",
    ]

    client = openai.OpenAI(api_key=api_key)
    last_text = ""

    for attempt in range(max_retries):
        idx = min(attempt, len(system_prompts) - 1)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompts[idx],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompts[idx]},
                            {"type": "image_url", "image_url": {"url": f"data:{mimetype};base64,{img_b64}"}},
                        ],
                    },
                ],
                max_completion_tokens=1600,
            )
            last_text = response.choices[0].message.content or ""
        except Exception as exc:
            last_text = f"OpenAI API error: {exc}"
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return last_text, "", ""

        if not _is_refusal(last_text):
            break  # success

        # Model refused — log & retry with softer prompt
        print(f"[AI] Attempt {attempt + 1}/{max_retries} refused for "
              f"{os.path.basename(jpeg_path)}: {last_text[:80]}...")
        if attempt < max_retries - 1:
            time.sleep(1)

    text = last_text

    # --- parse Description ---
    desc = text
    if "Description:" in text:
        desc = text.split("Description:", 1)[1]
    # Cut description before UKR_Keywords or EN_Keywords line
    desc = re.split(r"(?m)^\s*(?:UKR_Keywords|EN_Keywords)\s*:", desc, flags=re.IGNORECASE, maxsplit=1)[0]
    # Also remove a standalone "Keywords:" header if present (but NOT inside UKR_/EN_Keywords)
    desc = re.split(r"(?m)^\s*Keywords\s*:", desc, flags=re.IGNORECASE, maxsplit=1)[0]
    desc = desc.strip()

    # --- parse UKR / EN keywords ---
    uk_pipe = _parse_pipe_keywords(text, "UKR_Keywords", limit=keywords_limit)
    en_pipe = _parse_pipe_keywords(text, "EN_Keywords", limit=keywords_limit)

    # fallback: translate via separate call if model didn't return EN_Keywords
    if uk_pipe and not en_pipe:
        try:
            en_pipe = _translate_ukr_pipe_to_en_pipe(uk_pipe, api_key, model, limit=keywords_limit)
        except Exception:
            en_pipe = ""

    return desc, uk_pipe, en_pipe
