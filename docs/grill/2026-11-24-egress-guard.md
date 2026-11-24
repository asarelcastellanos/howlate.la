# Grill: egress guard

2026-11-24. One round of four questions through the question tool, then a confirmation.

## Scope

| Question | Answer |
|---|---|
| What prompted this? | The November 2026 bill reached $25.18 against a normal month of about $2. Runs on a laptop downloaded 259 GiB from `gs://howlate-raw` between 2026-11-16 and 2026-11-18. Egress cost $19.11 and Coldline retrieval cost $3.49. |
| What did the owner ask for? | "i'd like to use suggestions 1 and 2 and add not only those guards to the pipeline but add it to a doc or soemthign that any future claude session will read and they will see that we should never attempt to download data like that and we should just use a backfill-vm." |
| Which doc does every session read? | `CLAUDE.md` at the repo root. |
| How does the guard tell where it runs? | It asks the Google Cloud metadata server. This is an implementation detail and the owner was not asked. |

## Round 1

| # | Question | Answer |
|---|---|---|
| Q1 | What should the guard do when `arrivals` or `backfill` would download raw files outside Google Cloud? | Refuse, with an override flag. See [ADR-0001](../adr/0001-refuse-raw-downloads-outside-google-cloud.md). |
| Q2 | Should a small download, such as one service day, pass without the override? | No, refuse every size. See ADR-0001. |
| Q3 | Should the guard also cover `gs://howlate-derived`? | Raw bucket only. |
| Q4 | Which release ships it? | v0.5.2, as issue #184. |

## Confirmation

The owner chose "Yes, build it" for this summary. `arrivals` and `backfill` refuse any raw download from `gs://howlate-raw` outside Google Cloud, at every size, and print the gigabytes, the estimated cost and the `backfill-vm.sh` command. The `--allow-egress` flag lets a person force it. `gs://howlate-derived` stays unguarded. `CLAUDE.md` gains a rule that no session downloads the raw archive locally or passes the flag. It ships in v0.5.2 as one issue.
