# Decide whether to ask a question before choosing a team

[简体中文](README.md) | English

The previous experiment asked the model to choose between billing, technical support, delivery, and clarification in a single call. This experiment first asks whether the ticket can go directly to one team. If so, the model reads the original ticket again and chooses among the three teams.

## Results on the same 24 tickets

- **18 tickets could go directly to a team.** The previous prompt routed 4 correctly and asked for clarification on the other 14. The two-stage model routed 17 correctly. Its one department error was a request to correct a company name and tax number on an invoice, which it sent to technical support.
- **6 tickets needed a follow-up question.** The previous prompt asked for clarification on 5. The two-stage model sent 4 to technical support and 2 to delivery. For example, it chose technical support for “It failed again. Can somebody sort this out?”

Overall accuracy rose from 9/24 to 17/24. Of the 24 decisions, 13 changed from wrong to right and 5 from right to wrong. The model assigned recognizable requests more accurately but missed every required clarification. The two-stage procedure remains experimental. [Previous four-way results](../prompt-combined-v1/README.en.md)

## Reversing the first two options

The model chose the first option, “route to team,” on all 24 tickets in the first run. With “needs clarification” listed first, it still chose “route to team” for every ticket. Both orders produced the same final department for each ticket and used 48 calls each. A repeat of the original order reproduced all 48 model responses. The four-way comparison uses the 24 calls saved in the previous experiment. [Route first](route-first/) | [Clarification first](clarification-first/)

Both orders used identical wording. The department descriptions and their relative order were carried over from the previous experiment, along with the model revision, ticket texts, and reviewed labels. Labels were used only for scoring. All inference ran on a local CPU using the published weights. These 24 synthetic tickets have been used throughout development. Performance on new tickets is still unmeasured.

## Reproduce

With the pinned model and a completed local review, run these commands from the repository root. Each run saves its prompts, per-ticket requests and responses, scores, and metadata in a new directory under `outputs/`.

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.two_stage_routing --gate-order route-first
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.two_stage_routing --gate-order clarification-first
```
