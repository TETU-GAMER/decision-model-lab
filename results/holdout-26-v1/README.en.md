# How did the 26% clarification cutoff perform on new tickets?

[简体中文](README.md) | English

The model requested clarification on 11 of 24 new tickets. The reviewer had marked all 11 as assignable to a team. All 3 tickets that required a question went straight to a department. Overall, 8/24 decisions matched the review (33.3%).

## The same cutoff on two batches

- **How many required clarifications did the model catch?** It caught 5/6 (83.3%) on the development set and 0/3 (0%) on the new batch. All three missed tickets asked for two issues involving different teams to be addressed. One went to technical support and two went to delivery.
- **How many assignable tickets got an unnecessary question?** The count rose from 3/18 (16.7%) on the development set to 11/21 (52.4%) on the new batch. The latter included all six tickets the reviewer assigned to delivery. Of the ten remaining assignable tickets, eight went to the right team and two to the wrong team.

The same configuration matched 19/24 development labels. The cutoff was chosen after examining those development labels. Only three tickets in the new synthetic batch were marked as requiring clarification, which limits what this run can tell us about missed questions in real support traffic. [Development cutoff comparison](../clarification-thresholds-v1/README.en.md)

## Two decisions

A customer who paid with a gift card and a debit card wanted to know where a partial return would be refunded. Its clarification score of 26.09% put it just over the cutoff, triggering a question. Another customer needed to supply a flat number for a delivery and trace a missing account credit. That ticket scored 17.78%, so both requests went to delivery. [Per-ticket model responses](predictions.jsonl)

## Experiment setup

All 24 tickets were newly written synthetic examples. The reviewer classified them three at a time and completed the batch before inference began. The model used the original English text and the pinned weights without fine-tuning. The first step listed “route to team” first. A clarification score at or above 26% triggered a question, and only tickets below the cutoff went on to department selection. All 24 first-step calls and 13 department calls succeeded. [Frozen protocol](../../data/holdout_protocol_v1.json) · [Prompts](prompts.json)

With the pinned model and a completed local review, run `python -X utf8 -m experiments.two_stage_routing --holdout` from the repository root. Different review labels can change the evaluation scores. [Scores and confusion matrix](scores.json) · [Model revision and environment](metadata.json)

## Adding one sentence about priority

Both versions of the flat-number and missing-credit ticket kept the original closing sentence, “I'd like both sorted out today.” The second version appended only `Please check the missing credit first.` Both ran afresh with the same model weights and 26% cutoff.

- **Original.** The expected action was clarification. The score for clarification was 17.78%, so the model went on to choose delivery. Both model responses reproduced the earlier run.
- **Credit first.** The expected team was billing. The clarification score was 21.90%, so the model proceeded to choose a team. Billing rose from 13.46% to 19.05% and delivery fell from 74.00% to 68.82%. Delivery still won.

Both final choices missed the expected action. The original ticket went wrong at the clarification step. The edited ticket went wrong at department selection. Run `python -X utf8 -m experiments.priority_pair` to reproduce this pair. [Both inputs and raw responses](priority-pair.json)

## Moving the credit request to the beginning

Both tickets explicitly asked to check the missing credit first and should go to billing. Only the position of the sentence `Please check the missing credit first.` changed. All other wording, punctuation, and sentence order stayed the same. Each version ran once with the same weights, prompts, candidate order, and 26% clarification cutoff.

- **Sentence last.** Clarification scored 21.90%. At department selection, billing scored 19.05% and delivery scored 68.82%. The model chose delivery, reproducing both responses from the previous run.
- **Sentence first.** Clarification scored 19.48%. Billing rose to 21.00%, but delivery also rose, to 69.88%, and was selected again.

Moving the explicit priority to the beginning did not correct this ticket's routing. Run `python -X utf8 -m experiments.priority_pair --compare-position` to reproduce the comparison. [Inputs and raw responses by sentence position](priority-position.json)

## Removing the delivery request

We kept the opening priority sentence from the previous run, removed the clause about the courier needing a flat number, and changed “both” to “this” to retain the deadline. The single-issue ticket read:

> Please check the missing credit first. Last month's credit is missing from my balance. I'd like this sorted out today.

- **Both issues.** Clarification scored 19.48%. The model went on to choose delivery (69.88%), with billing at 21.00%. Both responses reproduced the previous run.
- **Missing credit only.** Clarification rose to 26.81%, above the fixed 26% cutoff. The router stopped at the first step and requested clarification.

To check the department decision separately, we passed the same single-issue text directly to the original department step. It chose billing (50.59%), followed by delivery (28.70%) and technical support (20.70%). For this ticket the first step prevented that billing assignment. Both routing runs reproduced their responses on replay with the original model weights. Run `python -X utf8 -m experiments.priority_pair --compare-credit-only` to reproduce the comparison. [Routing traces and separate department check](credit-only.json)
