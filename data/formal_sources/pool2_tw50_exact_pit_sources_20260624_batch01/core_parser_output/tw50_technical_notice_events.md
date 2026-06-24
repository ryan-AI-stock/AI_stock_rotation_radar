# TW50 Technical Notice Event Ingestion

- readiness_status: `events_ready_pending_baseline_snapshot`
- event_rows: `62`
- accepted_event_rows: `62`
- blocked_event_rows: `0`

## Core Boundary

- These rows are exact-candidate Taiwan Index technical notice events.
- They are not sufficient for formal Pool2 replay until a point-in-time baseline snapshot exists on or before the first event.
- Yuanta 0050 holdings/monthly reports remain proxy candidates and must not be mixed into exact TW50 constituents.

## Blockers

- PIT interval build still requires an official baseline constituent snapshot on or before the first event
