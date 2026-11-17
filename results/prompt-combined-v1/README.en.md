# Combining the instruction and candidate description edits

[简体中文](README.md) | English

The combined prompt reduced incorrect clarification predictions from 18 to 14 relative to the original. It kept 5 of the 6 required clarifications and matched 9 of the 24 labels, the same counts as editing the candidate description alone.

## Setup

The run reused the same 24 tickets, reviewed labels, model revision, and candidate order. It combined the exact instruction and `needs_clarification` description tested separately in the earlier run. All 24 new calls succeeded. The first three conditions below come from the saved run on the same tickets. [Exact combined prompt](prompts.json) | [Earlier results](../prompt-ablation-v1/README.md)

## Results

The development set has 18 tickets that can be routed directly and 6 that require clarification.

- **Original** matched 6/24 labels, with 18/18 incorrect clarifications and 6/6 required clarifications kept.
- **Instruction only** matched 8/24 labels, with 15/18 incorrect clarifications and 5/6 required clarifications kept.
- **Candidate description only** matched 9/24 labels, with 14/18 incorrect clarifications and 5/6 required clarifications kept.
- **Combined** matched 9/24 labels, with 14/18 incorrect clarifications and 5/6 required clarifications kept.

The combined prompt routed the ticket about both a damaged parcel and a duplicate charge (`fresh-012`) to delivery. The policy calls for asking which issue to handle first when the customer gives both issues equal priority.

Compared with editing only the candidate description, the combined prompt correctly routed the ticket about two weeks without a tracking update (`fresh-008`) to delivery. It switched the ticket about a parcel stuck at the sorting centre for six days (`order-009`) to clarification. Those two changes offset each other. The results describe the same synthetic development set used in the earlier experiments.

## Reproduce

With the pinned model and completed local reviews in place, run from the repository root:

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.prompt_ablation --variant combined
```

[Full requests and responses](predictions.jsonl) | [Scores and confusion matrix](scores.json) | [Run metadata](metadata.json)
