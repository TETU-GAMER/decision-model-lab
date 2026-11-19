# decision-model-lab

[简体中文](README.md) | English

A local ticket-routing experiment built around an existing decision model. Given a support ticket, it selects billing, technical support, delivery, or needs clarification and records the model's scores for each option.

The current routing policy follows the customer's stated priority. It asks for clarification when the ticket gives too little detail to identify a team or presents equally important issues for different teams. The project uses the published model weights for inference.

## Results

- **Can a score cutoff identify tickets that need a question?** On these 24 development tickets, the best cutoff that preserved all 17 correct department assignments caught only 1 of 6 required clarifications. Catching all 6 preserved at most 8 of the 17. [Clarification scores and cutoffs](results/clarification-thresholds-v1/README.en.md)
- **Deciding whether to ask a question before choosing a team.** On the same 24 tickets, the two-stage model sent 17 of 18 assignable tickets to the right team. It also sent all six tickets that needed a follow-up straight to a team. Reversing the two options in the first step left every final decision unchanged. This version is experimental. [Two-stage routing experiment](results/two-stage-v1/README.en.md)
- **Prompt wording.** On the same 24 tickets, the original prompt incorrectly requested clarification 18 times. Editing the instruction reduced that count to 15. Editing the candidate description alone and combining both edits each reduced it to 14. The combined prompt matched 9 labels and kept 5 of the 6 required clarifications. [Combined prompt experiment](results/prompt-combined-v1/README.en.md) | [Isolated edits](results/prompt-ablation-v1/README.md)
- **Candidate order.** Two exploratory batches used 600 local model calls in total. Averaging four rotations reduced the number of tickets whose selected team changed from 7/12 to 1/12 in the first batch and from 6/12 to 2/12 in the second. Sorting by candidate ID gives the model a fixed order with one call per ticket. [Strategy comparison](results/strategy-comparison-v1/README.md)
- **Development-set accuracy.** On 24 reviewed tickets, the keyword baseline matched 24/24 labels. The model matched 6/24 with the original order, 7/24 with fixed sorting, and 6/24 with four rotations. The original order and four rotations both selected needs clarification for every ticket. [Development evaluation](results/development-evaluation-v1/README.md)

These results come from small, synthetic development batches. The 24 labels were supplied or confirmed by the reviewer, sometimes with AI explanations. The keyword baseline was built with access to the development examples. Independent test accuracy remains unknown.

## Run locally

The commands below were verified on Windows x64 with Python 3.11 and CPU inference. Install Git and Python, then run:

```powershell
git clone https://github.com/TETU-GAMER/decision-model-lab.git
cd decision-model-lab
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
& '.\.venv\Scripts\python.exe' -X utf8 download_model.py
```

The download is approximately 2.32 GB. It uses the pinned model revision and verifies the files before the inference entry points load the custom code. Inference runs locally and writes responses to `outputs/`.

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 route_ticket.py --strategy single --text 'My parcel was delivered to the wrong address.'
```

The available strategies are `single`, `sorted`, `cyclic4`, and `all24`, requiring 1, 1, 4, and 24 model calls per ticket respectively. `route_ticket.py` defaults to `cyclic4` and reads `data/task_policy_v1.json`. It saves every model response and requires all calls to succeed before averaging their scores. The model scores are uncalibrated.

The original teaching example has a separate entry point. Its `--validate-only` option checks the input structure without loading the model. [First model response](results/demo-001.json)

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 run_example.py --device cpu
```

## Review and evaluate

A fresh batch of 24 synthetic tickets tests the 26% cutoff chosen on the development set. The gate lists “route to team” first and asks for clarification at or above 26%. The reviewer sees three tickets at a time. Inference starts after all labels are recorded. We count how many required clarifications are caught and how many assignable tickets receive an unnecessary question, each against its own group size. [Frozen experiment settings](data/holdout_protocol_v1.json)

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 review_cases.py --queue data/holdout_review_v1.json --local-dir local_review/holdout_v1
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.two_stage_routing --holdout
```

The review tool shows three tickets per session by default, with a Chinese reading aid. Choose `b`, `t`, `d`, or `c` for billing, technical support, delivery, or clarification. A reason is optional for the new batch and required for the development set below. Labels and reasons are stored in the Git-ignored `local_review/` directory.

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 review_cases.py
& '.\.venv\Scripts\python.exe' -X utf8 run_evaluation.py --validate-only
& '.\.venv\Scripts\python.exe' -X utf8 run_evaluation.py
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.prompt_ablation
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.prompt_ablation --variant combined
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.two_stage_routing
```

The evaluation requires a complete review and produces accuracy, macro-F1, technical failure counts, and a confusion matrix. A fresh clone needs its own completed reviews. [Review and evaluation guide](docs/REVIEW_AND_EVALUATION.md)

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.order_sensitivity
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.compare_routing_strategies --run-dir results/order-probe-v1
```

## Model provenance

vLLM Semantic Router publishes Decision-1.0-Kai-0.6B. This project pins revision `ee45160abf994a9eca0e59495bd9b4bf08c1571a`. The checkpoint and upstream Python files are downloaded from Hugging Face. [Pinned model files](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/tree/ee45160abf994a9eca0e59495bd9b4bf08c1571a)

The manifest records file sizes and hashes. The provenance notes cover licensing and the Transformers loading workaround. [Model manifest](model-lock.json) | [Provenance notes](MODEL_PROVENANCE.md)
