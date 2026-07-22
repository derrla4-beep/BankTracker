# BankTracker JSON Schemas

## data/firms.json
```json
{
  "firms": [
    {
      "id": "goldman-sachs",
      "name": "Goldman Sachs",
      "tier": "BB",
      "careers_url": "https://www.goldmansachs.com/careers/students",
      "insight_programs_url": "https://...",
      "notes": ""
    }
  ]
}
```
- `id`: kebab-case, unique. `tier`: `"BB"` | `"EB"` | `"MM"`.
- `insight_programs_url` may be `null` if the firm has no insight-program page.

## data/programs.json
```json
{
  "programs": [
    {
      "id": "goldman-sachs-2028-sa-ib",
      "firm_id": "goldman-sachs",
      "name": "2028 Summer Analyst — Investment Banking (NYC)",
      "type": "SA",
      "target_summer": 2028,
      "historical_opens": { "2026": "2025-03-04", "2027": "2026-03-02" },
      "predicted_open": "2027-03-01",
      "confidence": "high",
      "status": "predicted",
      "application_url": null,
      "sources": ["https://..."],
      "last_checked": null,
      "notes": ""
    }
  ]
}
```
- `type`: `"SA"` | `"insight"`. `target_summer`: int (2027 or 2028).
- `historical_opens`: map of cycle-year → the date that cycle's app opened. May be `{}`.
- `confidence`: `"high"` (2+ historical years), `"medium"` (1 year), `"unverified"` (0 years).
- `status`: `"predicted"` | `"open"` | `"closed"` | `"unverified"`.
- `predicted_open` must be `null` when confidence is `"unverified"`; otherwise a date. Unverified-confidence programs must have status `"unverified"` unless verifiably `"open"` (with `application_url`) or `"closed"`.
- `application_url`: null until status is `"open"`.
- `last_checked`: ISO date of last live check, or null.

## data/bu-events.json
```json
{
  "events": [
    {
      "id": "gs-questrom-info-session-2026-09-15",
      "firm_id": "goldman-sachs",
      "title": "Goldman Sachs Info Session @ Questrom",
      "date": "2026-09-15",
      "time": "18:00",
      "location": "Questrom School of Business",
      "source_url": "https://...",
      "added": "2026-07-22"
    }
  ]
}
```
- `firm_id` may be `null` for multi-firm events (career fairs). `time`/`location` may be `null`.

## state/calendar-sync.json
```json
{
  "programs": {
    "goldman-sachs-2028-sa-ib": {
      "t_minus_4w": "<google event id>",
      "t_minus_1w": "<google event id>",
      "t_day": "<google event id>"
    }
  },
  "bu_events": { "gs-questrom-info-session-2026-09-15": "<google event id>" }
}
```
- Keys are program/event ids from the data files. Missing key = no events created yet.
- Any of the three alert slots may be absent (e.g., T−4w was already in the past at seed time).
