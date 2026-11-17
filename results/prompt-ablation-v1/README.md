# Prompt ablation on the reviewed development set

Both wording edits reduced incorrect clarification predictions on the same 24 tickets. The candidate description edit corrected four of the original errors, all delivery tickets. The instruction edit corrected three, one billing ticket and two delivery tickets.

## Setup

Each ticket was sent to the pinned Kai model once per condition. The model, ticket text, candidate IDs, candidate order, and scoring labels were held fixed. The rerun reproduced all 24 original choices from the previous development evaluation. The three conditions completed 72 CPU inference calls with zero technical failures.

- **Original.** `ticket-routing-v1` instruction and candidate descriptions.
- **Instruction only.** Reword the task to lead with matching the main issue to a team, then state when to clarify. Use the original descriptions.
- **Clarification description only.** Reword `needs_clarification` as a follow-up action and say when to ask. Use the original instruction and the other three descriptions.

The two edits were chosen before this run. This comparison tests one wording per field. A combined edit and alternative wordings would require separate runs. [Exact prompts](prompts.json)

## Results

Six tickets have a clarification label and 18 can be routed directly.

- **Original.** 6/24 matches, macro-F1 0.100. Clarification was selected on 24/24 tickets, including 18 incorrect clarifications and all 6 correct ones.
- **Instruction only.** 8/24 matches, macro-F1 0.279. Clarification was selected on 20/24 tickets, including 15 incorrect clarifications and 5 correct ones.
- **Clarification description only.** 9/24 matches, macro-F1 0.282. Clarification was selected on 19/24 tickets, including 14 incorrect clarifications and 5 correct ones.

Both edits routed the same mixed ticket to delivery even though the customer requested help with two equally important issues, a damaged parcel and a duplicate charge. Both edits still sent all six technical support tickets to clarification.

These runs isolate the effect of the two tested wordings. The description edit scored one more correct ticket than the instruction edit on this set. The sample size and the single wording per field limit conclusions about which field matters more in general. The tickets are synthetic development examples that were used in earlier experiments. The reviewer supplied or confirmed the labels, sometimes with AI explanations.

## Reproduce

Complete the review queue and set up the pinned model using the repository instructions. Then run from the repository root:

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.prompt_ablation
```

The output contains the full requests and responses, run metadata, and scores. Scoring uses the annotations stored locally. [Raw predictions](predictions.jsonl) · [Scores and confusion matrices](scores.json) · [Run metadata](metadata.json)
