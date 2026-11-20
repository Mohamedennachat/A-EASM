# The diff engine (alert-fatigue suppression)

The pipeline writes the full scan history every run, but it only raises alerts
for findings it has not seen before. This keeps the team from being paged about
the same issue on every cycle.

## How it works

Each finding is reduced to a stable key:

```
finding_key = category | host | identifier | url
```

The key is upserted into the `findings` table. The insert reports whether the
row was new in the same statement:

```sql
INSERT INTO findings (...) VALUES (...)
ON CONFLICT (finding_key) DO UPDATE
  SET last_seen = now(), times_seen = times_seen + 1
RETURNING finding_key, (xmax = 0) AS is_new;
```

`xmax = 0` is true only for rows that were actually inserted, so `is_new`
flags genuinely new findings. The "Diff Upsert" node runs this statement and
the "Apply Diff" node keeps only the new findings for the alert branch.

## Where it lives in the workflow

`Merge All Results` -> `Diff Prepare` -> `Diff Upsert` -> `Apply Diff` ->
`Prepare DB Rows` -> `Save to PostgreSQL` -> `IF New Findings`.

The full results always land in the `scan_*` history tables. Only the rows that
came back with `is_new = true` continue to the email, Discord, and Jira nodes.
