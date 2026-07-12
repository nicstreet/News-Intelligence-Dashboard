# Manual Frontend Test Checklist

Run:

```bash
uvicorn news_intelligence.main:app --reload
```

Then open `http://127.0.0.1:8000/`.

## Acceptance Checks

- Select each predefined fixture and click `Analyse`.
- Confirm pipeline stages progress to completed.
- Select each pipeline stage and inspect the JSON payload.
- Confirm event summary labels show direction, status, confidence, quality, surprise, novelty, persistence, and roles.
- Sort instrument impacts by symbol, strength, relevance, and confidence.
- Confirm the signal panel is separate from the event interpretation.
- Confirm evidence shows source credibility, article count, duplicate count, confirmation status, and contradictions.
- Confirm duplicate syndicated stories create one cluster with twenty articles and nineteen duplicates.
- Confirm the denial fixture shows contradictions and a veto-capable signal.
- Confirm the price-action rejection fixture shows a veto-capable signal.
- Confirm recent events can be refreshed and selected.
- Confirm source status renders fixture connector rows.
- Confirm raw JSON can be copied and downloaded.
- Confirm the developer panel can run a health check and simulate backend failure.
- Confirm the page remains usable at 1366 x 768 without main-page horizontal scrolling.
