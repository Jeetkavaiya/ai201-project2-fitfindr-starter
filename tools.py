"""
tools.py
Three FitFindr tools — fully implemented.
"""

import os
import re
from dotenv import load_dotenv
from groq import Groq
from utils.data_loader import load_listings

load_dotenv()

def _get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set. Add it to a .env file in the project root.")
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ──────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.
    Returns a list of matching dicts sorted by relevance, or [] if none found.
    """
    try:
        listings = load_listings()
    except Exception as e:
        print(f"[search_listings] Failed to load listings: {e}")
        return []

    # Step 1 — filter by price
    if max_price is not None:
        listings = [l for l in listings if l.get("price", 9999) <= max_price]

    # Step 2 — filter by size (case-insensitive substring match)
    if size:
        size_lower = size.lower()
        listings = [
            l for l in listings
            if size_lower in str(l.get("size", "")).lower()
        ]

    # Step 3 — score by keyword overlap with description
    keywords = re.findall(r"\w+", description.lower())

    def score(listing):
        searchable = " ".join([
            listing.get("title", ""),
            listing.get("description", ""),
            listing.get("category", ""),
            listing.get("brand", "") or "",
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
        ]).lower()
        return sum(1 for kw in keywords if kw in searchable)

    scored = [(score(l), l) for l in listings]
    # Step 4 — drop zero-score items
    scored = [(s, l) for s, l in scored if s > 0]
    # Step 5 — sort highest first
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ───────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Suggests 1-2 outfit combinations using the new item and the user's wardrobe.
    Handles empty wardrobe gracefully with general styling advice.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"[suggest_outfit error] {e}"

    title = new_item.get("title", "this item")
    description = new_item.get("description", "")
    style_tags = ", ".join(new_item.get("style_tags", []))
    colors = ", ".join(new_item.get("colors", []))
    category = new_item.get("category", "")

    items = wardrobe.get("items", [])

    if not items:
        # Empty wardrobe — general styling advice
        prompt = f"""You're a thrift fashion stylist. A user just found this secondhand item:

Item: {title}
Description: {description}
Style tags: {style_tags}
Colors: {colors}
Category: {category}

They haven't told you what's in their wardrobe yet. Give them 1-2 specific outfit ideas:
what types of bottoms, shoes, and outerwear would pair well with this piece.
Name specific clothing archetypes (e.g. "wide-leg jeans", "chunky white sneakers") rather than being vague.
Keep it to 3-5 sentences total."""
    else:
        # Wardrobe available — suggest specific combinations
        wardrobe_lines = []
        for w in items:
            tags = ", ".join(w.get("style_tags", []))
            notes = f" ({w['notes']})" if w.get("notes") else ""
            wardrobe_lines.append(f"- {w['name']} [{w['category']}]{notes} — tags: {tags}")
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = f"""You're a thrift fashion stylist. A user just found this secondhand item:

Item: {title}
Description: {description}
Style tags: {style_tags}
Colors: {colors}
Category: {category}

Their current wardrobe:
{wardrobe_text}

Suggest 1-2 complete outfit combinations using the new item and specific named pieces from their wardrobe.
Reference pieces by name. Describe the vibe of each outfit in one sentence.
Keep the whole response to 4-6 sentences."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[suggest_outfit error] Could not generate outfit suggestion: {e}"


# ── Tool 3: create_fit_card ──────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generates a short, shareable Instagram/TikTok-style caption for the outfit.
    Returns a descriptive error string if outfit is empty — never raises.
    """
    # Guard against empty outfit
    if not outfit or not outfit.strip():
        return "[create_fit_card error] Cannot generate a fit card — outfit suggestion is empty. Please run suggest_outfit first."

    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"[create_fit_card error] {e}"

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price", "")
    platform = new_item.get("platform", "a thrift app")
    price_str = f"${price:.0f}" if price else ""

    prompt = f"""You're writing a short caption for a thrift fashion post on Instagram or TikTok.

The thrifted item: {title}{f', {price_str}' if price_str else ''} from {platform}
The outfit: {outfit}

Write a 2-3 sentence caption that:
- Sounds like a real person wrote it (casual, genuine, not a product description)
- Mentions the item name, price, and platform naturally — each only once
- Captures the specific vibe of the outfit
- Ends with a relevant emoji or two

Do NOT use hashtags. Do NOT say "caption:" or quote the outfit back verbatim."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.95,  # high temp = variation on repeated calls
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[create_fit_card error] Could not generate fit card: {e}"