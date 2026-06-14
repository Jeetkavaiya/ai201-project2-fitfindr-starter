# FitFindr — planning.md

> This document was completed before writing any implementation code.
> The spec and agent diagram below were used to direct AI tools to generate the implementation.

***

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (`data/listings.json`) for secondhand items that match a natural language description, optional size filter, and optional price ceiling. Returns results sorted by relevance so the agent can pick the best match.

**Input parameters:**
- `description` (str): Keywords describing what the user is looking for (e.g., "vintage graphic tee", "90s track jacket"). Used for keyword scoring against title, description, style_tags, category, colors, and brand fields.
- `size` (str | None): Size string to filter by, or `None` to skip size filtering. Matching is case-insensitive substring (e.g., "M" matches "S/M", "M/L"). Pass `None` when the user doesn't specify a size.
- `max_price` (float | None): Maximum price (inclusive), or `None` to skip price filtering. Compared against the listing's `price` (float) field.

**What it returns:**
A `list[dict]` of matching listing dicts, sorted highest relevance first. Each dict contains:
- `id` (str), `title` (str), `description` (str), `category` (str)
- `style_tags` (list[str]), `size` (str), `condition` (str)
- `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str)

Returns an empty list `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
If the list is empty, the planning loop immediately sets `session["error"]` to a message that tells the user exactly which filters produced no results (e.g., "No listings found matching size XXS and max price $5") and suggests specific adjustments (try a different keyword, remove the size filter, raise the price ceiling). The loop returns early and does **not** proceed to `suggest_outfit`.

***

### Tool 2: suggest_outfit

**What it does:**
Calls the Groq LLM (`llama-3.3-70b-versatile`) to generate 1–2 complete outfit combinations using the selected thrifted item and the user's wardrobe. Adapts its prompt based on whether the wardrobe is populated or empty.

**Input parameters:**
- `new_item` (dict): A listing dict — the item the user is considering buying (the top result from `search_listings`). Used for its `title`, `description`, `style_tags`, `colors`, and `category`.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts (each with `name`, `category`, `colors`, `style_tags`, `notes`). May be empty — handled gracefully.

**What it returns:**
A non-empty `str` with 1–2 outfit suggestions. If the wardrobe is populated, suggestions name specific wardrobe pieces. If the wardrobe is empty, suggestions describe clothing archetypes (e.g., "wide-leg jeans", "platform sneakers") that would complement the item.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the LLM is prompted for general styling archetypes rather than wardrobe-specific combinations — the function always returns a non-empty string. If the LLM call fails (network error, API key issue), the function returns a descriptive error string prefixed with `[suggest_outfit error]` rather than raising an exception.

***

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM to generate a short, casual 2–3 sentence Instagram/TikTok-style caption for the outfit. Uses `temperature=0.95` to ensure variation across repeated calls on the same input.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit()`. Must be non-empty — the function checks this before calling the LLM.
- `new_item` (dict): The listing dict for the thrifted item. Used for its `title`, `price`, and `platform` to include naturally in the caption.

**What it returns:**
A 2–3 sentence `str` caption that sounds like a real OOTD post — mentioning item name, price, and platform once each, capturing the outfit vibe, and ending with an emoji. Different every time for different inputs.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the function immediately returns a descriptive error string (`[create_fit_card error] Cannot generate a fit card — outfit suggestion is empty`) without calling the LLM. LLM call failures return an error string rather than raising an exception.

***

### Additional Tools (if any)

None implemented for the required scope. See stretch features section of the project spec for potential additions (price comparison, style memory, trend awareness).

***

## Planning Loop

**How does your agent decide which tool to call next?**

The loop in `run_agent()` uses explicit conditional branching — not LLM reasoning — to decide what to call next. Here is the exact logic:

1. **Parse the query** using regex to extract `size`, `max_price`, and a cleaned `description`. This happens unconditionally on every call.

2. **Call `search_listings(description, size, max_price)`.**
   - If `results == []`: set `session["error"]` to a specific message listing the filters used and suggestions for broadening the search. **Return the session immediately.** Do NOT proceed to step 3.
   - If `results` is non-empty: set `session["selected_item"] = results[0]` and continue.

3. **Call `suggest_outfit(session["selected_item"], wardrobe)`.**
   - Always called when step 2 returned results — the empty wardrobe case is handled inside the tool, not here.
   - Store result in `session["outfit_suggestion"]`.

4. **Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`.**
   - Only called if we reached this point (i.e., steps 2 and 3 succeeded).
   - Store result in `session["fit_card"]`.

5. **Return the session.** The caller checks `session["error"]` first; if `None`, all three output fields are populated.

The key behavioral branch: **the agent calls either 1 tool (search only, on failure) or all 3 tools (on success)**. It never calls `suggest_outfit` with empty input.

***

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session(query, wardrobe)` at the start of `run_agent()`. The dict is mutated in place as each step completes:

| Key | Set when | Used by |
|-----|----------|---------|
| `session["parsed"]` | After regex parsing | `search_listings` call |
| `session["search_results"]` | After `search_listings` | Branching logic (empty check) |
| `session["selected_item"]` | After picking `results[0]` | `suggest_outfit`, `create_fit_card`, `app.py` display |
| `session["wardrobe"]` | At init (from `run_agent` arg) | `suggest_outfit` |
| `session["outfit_suggestion"]` | After `suggest_outfit` | `create_fit_card`, `app.py` display |
| `session["fit_card"]` | After `create_fit_card` | `app.py` display |
| `session["error"]` | On early exit | `app.py` display, loop termination |

No tool receives values through its own return value being re-parsed — the session dict is the single source of truth. `app.py`'s `handle_query()` reads directly from `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]` to populate the three Gradio output panels.

***

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the combined description + size + price filters | Sets `session["error"]` to: *"No listings found matching [filters used]. Try broadening your search — remove the size filter, raise your price ceiling, or use different keywords."* Returns early. `suggest_outfit` is never called. |
| `suggest_outfit` | `wardrobe["items"]` is empty (new user) | Switches to a general-styling prompt: asks the LLM for clothing archetypes that pair well with the item instead of named wardrobe pieces. Always returns a useful string. |
| `create_fit_card` | `outfit` string is empty or whitespace-only | Returns `"[create_fit_card error] Cannot generate a fit card — outfit suggestion is empty. Please run suggest_outfit first."` — no LLM call made, no exception raised. |

***

## Architecture

```
User natural language query
    │
    ▼
run_agent(query, wardrobe)
    │
    ├─ Step 1: _new_session() → session dict initialized
    │          session = { query, parsed, search_results, selected_item,
    │                      wardrobe, outfit_suggestion, fit_card, error }
    │
    ├─ Step 2: Regex parse → session["parsed"]
    │          { description (str), size (str|None), max_price (float|None) }
    │
    ├─ Step 3: search_listings(description, size, max_price)
    │              │
    │              ├── results == []  ──────────────────────────────────────┐
    │              │   session["error"] = "No listings found matching..."   │
    │              │   return session  ◄──────────────────────────────────-─┘
    │              │                        (early exit — error path)
    │              │
    │              └── results = [item, ...]
    │                  session["search_results"] = results
    │                  session["selected_item"]  = results[0]
    │
    ├─ Step 4: suggest_outfit(selected_item, wardrobe)
    │              │
    │              ├── wardrobe["items"] == []
    │              │   → LLM prompt: general styling archetypes
    │              │
    │              └── wardrobe["items"] populated
    │                  → LLM prompt: specific named-piece combinations
    │
    │              session["outfit_suggestion"] = <LLM response str>
    │
    ├─ Step 5: create_fit_card(outfit_suggestion, selected_item)
    │              │
    │              ├── outfit == ""  → return error string (no LLM call)
    │              │
    │              └── outfit populated → LLM prompt (temp=0.95)
    │
    │              session["fit_card"] = <LLM caption str>
    │
    └─ Step 6: return session
                   │
                   ▼
             app.py handle_query()
                   │
                   ├── session["error"] set?  → panel 1: error message, panels 2+3: ""
                   │
                   └── success path:
                       panel 1: formatted listing (title, price, platform, size, condition, colors)
                       panel 2: session["outfit_suggestion"]
                       panel 3: session["fit_card"]
```

***

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **Tool: `search_listings`** — Used Perplexity AI. Provided: the Tool 1 spec block above (inputs, return value, failure mode) plus the `load_listings()` signature from `data_loader.py`. Asked it to implement the function using `load_listings()`, filtering by price and size before scoring by keyword overlap, dropping zero-score results. Verified before running: checked that all three filter parameters were used, that size matching was case-insensitive substring (to handle "S/M"), that zero-score items were dropped, and that the function returns `[]` not `None` on no match. Tested with 3 queries: a matching query, a price-too-low query, and a size-that-matches-nothing query.

- **Tool: `suggest_outfit`** — Used Perplexity AI. Provided: Tool 2 spec, the wardrobe schema from `wardrobe_schema.json` (fields: name, category, colors, style_tags, notes), and the listing dict field list. Asked it to implement two branching prompts — one for empty wardrobe (archetypes), one for populated wardrobe (named pieces). Verified: confirmed the empty-wardrobe branch uses a different prompt, confirmed it never crashes when `wardrobe["items"]` is `[]`, ran it with both `get_example_wardrobe()` and `get_empty_wardrobe()`.

- **Tool: `create_fit_card`** — Used Perplexity AI. Provided: Tool 3 spec and example caption style from the project description. Asked it to add the empty-outfit guard, use `temperature=0.95`, and include price/platform naturally. Verified: ran it 3 times on the same input and confirmed all three outputs were different.

**Milestone 4 — Planning loop and state management:**

Used Perplexity AI. Provided: the full Architecture diagram above and the Planning Loop + State Management sections. Asked it to implement `run_agent()` following the numbered steps exactly — regex parsing for size/price, branch on empty results, pass `session["selected_item"]` into `suggest_outfit` directly (no re-parsing), store all outputs in session. Verified before running: confirmed the code branches on `results == []` and returns early, confirmed it does not call all three tools unconditionally, confirmed `session["selected_item"]` is the exact dict passed to `suggest_outfit`. Tested both paths (happy path + no-results) using the CLI test block at the bottom of `agent.py`.

***

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Query parsing:**
`run_agent()` calls `_new_session()` and then runs regex over the query.
- Extracts: `max_price = 30.0`, `size = None` (none specified), `description = "I'm looking for a vintage graphic tee. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it"` (price token stripped).
- Stores in `session["parsed"]`.

**Step 2 — Search:**
Calls `search_listings("vintage graphic tee...", size=None, max_price=30.0)`.
- Loads all 40 listings, filters to those with `price <= 30`.
- Scores each by keyword overlap: "vintage", "graphic", "tee" score highly against items whose title/description/style_tags contain those words.
- Returns e.g. `[{"title": "Y2K Baby Tee — Butterfly Print", "price": 18.0, "platform": "depop", ...}, ...]` sorted by score.
- Stores in `session["search_results"]`. Sets `session["selected_item"] = results[0]