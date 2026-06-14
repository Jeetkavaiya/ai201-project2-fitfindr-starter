"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""
import re
from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    # Step 1 — init session
    session = _new_session(query, wardrobe)

    # Step 2 — parse query with regex (fast, no LLM token cost)
    # Extract size: look for patterns like "size M", "size XL", "in M", "size S/M"
    size_match = re.search(r"\bsize\s+([A-Za-z0-9/]+)", query, re.IGNORECASE)
    if not size_match:
        size_match = re.search(r"\bin\s+(XS|S|M|L|XL|XXL|S\/M|M\/L)\b", query, re.IGNORECASE)
    size = size_match.group(1).upper() if size_match else None

    # Extract max_price: look for "under $30", "$30", "under 30"
    price_match = re.search(r"(?:under\s+)?\$?\s*(\d+(?:\.\d+)?)", query, re.IGNORECASE)
    max_price = float(price_match.group(1)) if price_match else None

    # Clean description: strip size/price tokens for better keyword matching
    description = re.sub(r"\bsize\s+\S+", "", query, flags=re.IGNORECASE)
    description = re.sub(r"(?:under\s+)?\$\s*\d+(?:\.\d+)?", "", description)
    description = re.sub(r"\bin\s+(XS|S|M|L|XL|XXL|S\/M|M\/L)\b", "", description, flags=re.IGNORECASE)
    description = description.strip()

    session["parsed"] = {
        "description": description,
        "size": size,
        "max_price": max_price,
    }

    # Step 3 — search listings
    results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = results

    # Branch: no results → early exit with helpful message
    if not results:
        filters_used = []
        if size:
            filters_used.append(f"size {size}")
        if max_price is not None:
            filters_used.append(f"max price ${max_price:.0f}")
        filter_str = " and ".join(filters_used) if filters_used else "your description"
        session["error"] = (
            f"No listings found matching {filter_str}. "
            f"Try broadening your search — remove the size filter, raise your price ceiling, "
            f"or use different keywords (e.g. 'jacket' instead of 'blazer')."
        )
        return session

    # Step 4 — select top result
    session["selected_item"] = results[0]

    # Step 5 — suggest outfit
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit

    # Step 6 — create fit card
    fit_card = create_fit_card(outfit, session["selected_item"])
    session["fit_card"] = fit_card

    # Step 7 — return completed session
    return session

# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
