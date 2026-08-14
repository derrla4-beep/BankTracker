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
- `id`: kebab-case, unique.
- `tracks`: non-empty list, no duplicates, over `"IB"` | `"CF"` | `"DS"`. A firm
  may recruit on several tracks (Amazon runs both corporate-finance and
  data-science pipelines).
- `tier`: `"BB"` | `"EB"` | `"MM"` when `"IB"` is in `tracks`; otherwise must be
  present and `null`. Tier grades investment banks and has no meaning off that
  track.
- `sweep_cadence`: `"every_run"` | `"weekly"` when `tracks` holds any non-IB
  track; otherwise present and `null`. IB programs are paced by `predicted_open`
  instead.
- A *missing* `tier` or `sweep_cadence` key is an error, not an implicit null.
- `insight_programs_url` may be `null` if the firm has no insight-program page.

## data/programs.json
```json
{
  "profile": { "grad_year": 2029, "school": "Boston University", "notes": "" },
  "programs": [
    {
      "id": "goldman-sachs-2028-sa-ib",
      "firm_id": "goldman-sachs",
      "name": "2028 Summer Analyst — Investment Banking (NYC)",
      "type": "SA",
      "target_summer": 2028,
      "eligibility": {
        "grad_years": [2029],
        "verified": false,
        "source": null,
        "quote": null
      },
      "historical_opens": { "2026": "2025-03-04", "2027": "2026-03-02" },
      "predicted_open": "2027-03-01",
      "confidence": "high",
      "status": "predicted",
      "application_url": null,
      "sources": ["https://..."],
      "sightings": [
        {
          "date": "2026-07-27",
          "url": "https://.../2027-summer-analyst",
          "cycle": "Summer 2027",
          "grad_years": [2028],
          "note": "Prior cycle, live but not applicable — timing intel only."
        }
      ],
      "last_checked": null,
      "notes": ""
    }
  ]
}
```
- `profile.grad_year`: the student's graduation year. A program is only actionable if its `eligibility.grad_years` contains it.
- `track`: `"IB"` | `"CF"` | `"DS"`, and must be one of the owning firm's
  `tracks`. Programs carry the authoritative track because behavior is decided
  per posting and a firm may span several tracks.
- `type`: `"SA"` | `"insight"` | `"internship"`. `"SA"` is investment-banking
  only. `target_summer`: int (2027 or 2028).
- `eligibility.grad_years`: non-empty list of ints — which graduating classes the program is for. Defaults to `[2029]` (the tracker's premise) until a posting says otherwise.
- `eligibility.verified`: `true` only when the audience was read off a live posting; then `source` (URL) and `quote` (the posting's own words) are both required.
- `sightings`: live postings found for this program's firm that belong to a **different** cycle. Recording one never changes `status`, `confidence`, `predicted_open`, or `application_url`, and never creates a calendar event. Each entry needs `date`, `url`, `cycle`, and a non-empty `grad_years`.
- **Cycle gate:** `status: "open"` requires `eligibility.verified == true` **and** `profile.grad_year` ∈ `eligibility.grad_years`. Banks run a cycle ahead, so a live "2027 Summer Analyst" posting is for 2028 grads and belongs in `sightings`, not in `status`.
- Only a cycle's *actual* open date belongs in `historical_opens`. A date on which a posting was merely observed already-live is an upper bound and belongs in the sighting's `note`.
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

## state/open-questions.json
```json
{
  "questions": [
    {
      "id": "capital-one-fap-2026-08-13",
      "firm_id": "capital-one",
      "program_id": null,
      "track": "IB",
      "title": "2028 Summer Analyst",
      "url": "https://.../2028-summer-analyst",
      "reason": "no-quotable-line",
      "first_seen": "2026-08-13",
      "last_seen": "2026-08-19",
      "resolved": false
    }
  ]
}
```
- A live posting a run could not classify as either `open` or a wrong-cycle
  `sighting`. Exists so that nothing a run touched exits unreported — see the
  three-door rule in `ROUTINE.md` step 4.
- `reason`: `"eligibility-unreadable"` | `"no-quotable-line"` |
  `"title-body-mismatch"` | `"page-load-failed"` | `"prediction-overdue"` |
  `"unverified-seen-posted"`.
- `url` and `title` are required for every reason except `"prediction-overdue"`,
  which has no posting behind it and sets both to `null`.
- `program_id` may be `null`: the sweep can find a live posting at a firm that
  has no program row yet.
- `track`: `"IB"` | `"CF"` | `"DS"`.
- Recording one never changes `status`, `confidence`, `predicted_open`, or
  `application_url`, and never creates a calendar event.
- Entries are never deleted. Settle one by setting `resolved: true`; it stays as
  history and drops out of the digest. Re-seeing an unresolved item updates
  `last_seen`, never creates a second entry.
