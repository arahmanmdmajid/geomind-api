# AI design

## Principle: the AI chooses, the code computes

The language model is used for two narrow tasks only:

1. **Routing** — turn a question into one analysis block with parameters (JSON).
2. **Explaining** — rephrase facts our code already computed.

It never calculates distances, counts or areas, never writes code, and is never asked for facts it wasn't given. Every answer in the app carries a tag showing the block that ran, e.g. `coverage(target=facilities, distance_m=2000)`.

## Routing (`geomind/ai.py`)

- Model: Groq `openai/gpt-oss-120b`, `temperature=0`, JSON response format.
- The prompt lists the five blocks, their parameters and 18 worked examples, and states which topics are in scope.

### Guard rails (`normalize`)

The model's JSON is cleaned into known values, then corrected using the question's own wording. These rules come from real mistakes found in testing:

| Model slip | Correction |
|---|---|
| "Show **me** schools…" read as "measure from my location" | `from=me` is only kept when the question really asks about the user's position ("near me", "my location") |
| "Closest to medical facilities" read as "from me" | measured from facilities instead |
| "Within 5 km radius" / "this location" read as "from me" | measured from the map pin |
| "Show schools and facilities on a map" returned only schools | shows everything |
| Distance given in km where metres were expected (e.g. `2`) | multiplied to metres |

### Fallback

If there is no API key, the network fails, or the free tier returns HTTP 429, a keyword router produces the same blocks. The tests check it handles all 18 tester questions without refusing any, and still refuses off-topic questions ("What's the weather?"). Answers produced this way are tagged "keyword fallback" in the app.

## Explaining — grounded generation

The explainer receives the question and the computed facts only, with instructions to:

- use plain text (no markdown),
- use only the facts given — never add names, numbers, benchmarks or standards,
- mention at most five names,
- name the data source.

This was added after an early version invented a "GIS database layer" as its source. If the explainer fails, the computed facts are shown directly.

## What we measured

- 18 realistic questions written by testers: all routed to a valid block by the real model and by the keyword fallback.
- Groq's free tier rate-limits after roughly six quick questions; the fallback keeps the app answering.
