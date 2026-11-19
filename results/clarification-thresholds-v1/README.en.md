# Can first-stage scores identify tickets that need clarification?

[简体中文](README.md) | English

On these 24 development tickets, neither candidate order had a cutoff that caught all 6 required clarifications and preserved all 17 correct department assignments. When keeping the 17 assignments took priority, listing clarification first and asking at a score of 22% or above recovered 1 of the 6.

## How the two groups scored

The scores come from the clarification option in the first step of the saved two-stage runs. They are shown as percentages. Higher values indicate a stronger model preference for clarification. The scores have yet to be calibrated against observed outcomes. Of the 18 assignable tickets, 17 originally went to the right department and 1 went to the wrong department.

- **Route first.** The 6 tickets that needed clarification scored 20.72%–30.44%, with a median of 27.03%. The 18 assignable tickets scored 14.62%–32.95%, with a median of 22.84%. Required clarifications had a higher median, but an assignable ticket had the highest score overall.
- **Clarification first.** Required clarifications scored 15.09%–24.09%, with a median of 16.91%. Assignable tickets scored 10.82%–20.99%, with a median of 16.55%. Only one required clarification scored above every assignable ticket.

## What changes at different cutoffs?

A score at or above the cutoff sends a ticket to clarification. A lower score keeps the archived department choice. Each order had 24 distinct scores. Checking each one, plus an outcome that sent every ticket to a department, covered all 25 possible sets of decisions per order. Counts use the full-precision scores.

- **Keep all 17 correct assignments.** Route first recovered at most 0/6 clarifications. Clarification first recovered at most 1/6, for example with a 22% cutoff.
- **Catch all 6 clarifications.** Route first kept at most 8/17 correct assignments, for example at 20.72%. This sent 10 of the 18 assignable tickets to clarification, including 9 previously correct assignments and the 1 previous department error. Clarification first kept at most 6/17, for example at 15.09%, and sent 12 assignable tickets to clarification.
- **Maximize the total number correct.** At 26% with route first, the model would catch 5/6 required clarifications and keep 14/17 correct department assignments, for 19/24 correct overall. Three previously correct assignments would get unnecessary follow-up questions and the original department error would persist.

These cutoffs were examined with the labels from the same development set. The replay used the saved responses, with zero new model calls or fine-tuning. Performance on independent tickets remains unmeasured. [Two-stage runs](../two-stage-v1/README.en.md) · [Aggregate scores and full-precision boundaries](summary.json)

## Reproduce

Run the following command from the repository root with the local review that matches the archived runs. The script checks the model revision, policy, queue, reviews, and raw responses, then writes the full sweep for each order to a new directory under `outputs/`. This step requires only Python's standard library and the repository code.

```powershell
python -X utf8 -m experiments.clarification_thresholds
```
