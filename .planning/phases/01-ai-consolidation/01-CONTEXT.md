# Phase 1: AI Consolidation - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace Kimi (triage) and Google Gemini (classify) with `claude-opus-4-6` for all 3 AI stages. Single Anthropic SDK, single API key. No new features — pure AI stack consolidation with quality and reliability improvements.

</domain>

<decisions>
## Implementation Decisions

### Error Handling

- **Per-image errors:** Retry once automatically. If retry fails, skip the image and log the error (image path + error details) to a persistent error log file per job. Do NOT fail the whole job for individual image errors.
- **API down / rate-limited:** Retry up to 3 times with exponential backoff. If all 3 retries fail, fall back to flagging all remaining images as `has_defect=true` (conservative — send everything to classify).
- **JSON parse failure:** Treat as `has_defect=true` (safe side — flag for human review). Do not retry on parse failure.
- **Error visibility:** Show error count and failed image list in the final PDF report. Full transparency to wind farm operators.
- **Error log file:** Save a `errors.json` per job in the job directory for future model improvement analysis.

### Cost Guardrails

- **Image cap:** Maximum 500 images per job. Excess images are skipped with a warning in the report.
- **Cost estimate before running:** Show inspector estimated cost before pipeline starts (based on image count × estimated tokens per image × Anthropic pricing). Inspector can cancel before confirming.
- **Hard cost limit:** Configurable via `COST_LIMIT_USD` env var in Render. Pipeline stops and job fails gracefully if limit is exceeded mid-run.
- **Tile count:** Reduce from 8 tiles to **4 tiles per image** for triage. Opus 4.6 is smarter — fewer tiles sufficient, meaningful cost reduction.
- **Cost logging:** Log actual API cost per stage (triage, classify, analyze) and total cost to `state.json` after each job.

### Triage Sensitivity

- **Bias:** Favour recall over precision — missing a real defect is worse than a false alarm for wind farm operators.
- **Confidence threshold:** `0.3+` to flag an image as defective (aggressive — catch everything).
- **Offshore vs onshore:** Offshore turbines use a stricter threshold (`0.2+`) because offshore repairs are significantly more expensive. The turbine metadata `location_type` field will carry this (onshore/offshore). Planner to determine how this is set — either as an upload form field or inferred from GPS coordinates.

### Prompt Strategy

- **Full rewrite for Opus 4.6:** Do not adapt Kimi/Gemini prompts. Write new prompts that leverage Opus 4.6's strengths — richer reasoning, better instruction following, stronger vision capabilities.
- **Full context for all stages:** Every API call receives full context: turbine ID, blade, zone, position, inspection date, turbine model, and for offshore jobs — offshore flag.
- **Reasoning:** Triage returns JSON only for low/medium confidence. For high-confidence defects (confidence ≥ 0.7), include one sentence of reasoning in the response alongside the JSON.
- **Classification standard:** Use both IEC 61400 / Vestas Cat 0–4 AND a custom BDDA severity score. Output both in classify results. Map: Cat 0=0, Cat 1=1–2, Cat 2=3–4, Cat 3=5–7, Cat 4=8–10.

### Claude's Discretion

- Optimal prompt wording and structure for each stage (triage, classify, analyze) — Claude writes the best prompts for Opus 4.6's capabilities.
- `location_type` field implementation detail (form field vs GPS inference).
- Exact backoff timing for retry logic.
- Cost estimation formula (tokens × pricing calculation).

</decisions>

<specifics>
## Specific Ideas

- Error log files (`errors.json`) should accumulate across jobs to build a training dataset for future model improvement.
- Email notifications for errors were mentioned — deferred (requires auth from Phase 3).
- The offshore/onshore sensitivity split is a key differentiator for wind inspection — this should be prominent in the upload form and report.

</specifics>

<deferred>
## Deferred Ideas

- **Error notification emails:** User wants errors sent to a corresponding email. Deferred to Phase 3 (Auth) — requires knowing which inspector owns the job.
- **Automatic model improvement from error logs:** Using `errors.json` files to retrain or tune prompts. Future milestone.

</deferred>

---

*Phase: 01-ai-consolidation*
*Context gathered: 2026-03-04*
