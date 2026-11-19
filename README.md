# decision-model-lab

简体中文 | [English](README.en.md)

一个在本机运行的客服工单分类实验。输入一条工单，使用公开的决策模型在账单、技术支持、配送和需要澄清中选一项，并保存每项的分数。

按客户明确提出的优先事项分配工单。如果信息不足以确定部门，或多个同等重要的问题涉及不同部门，就选择需要澄清。

## 实验结果

- **澄清分数能分开两组工单吗？** 在这 24 条开发工单里，如果要保住原先分对的 17 条，最好的分界线只能找回 6 条该追问工单中的 1 条。如果要找回全部 6 条，最多保住 8 条。 [分数与分界线](results/clarification-thresholds-v1/README.md)
- **先判断要不要追问，再选部门。** 在同一批 24 条工单上，两步法把 18 条可分单工单中的 17 条送对了部门，但也把 6 条该追问的全部分走了。调换第一步的选项顺序，24 条的最终选择都一样。这版只用于实验。 [两步分单实验](results/two-stage-v1/README.md)
- **提示词对照。** 在同样的 24 条工单上，原版误判澄清 18 条，只改指令后是 15 条，只改候选描述后是 14 条，合并两处改动后也是 14 条。合并版答对 9 条，6 条本该澄清的工单保住了 5 条。 [合并实验](results/prompt-combined-v1/README.md) | [单独改动的对照](results/prompt-ablation-v1/README.md)
- **候选顺序。** 两批探索工单共运行 600 次本地推理。四次轮换取平均后，第一批会因换顺序而改选的工单从 7/12 条降到 1/12 条，第二批从 6/12 条降到 2/12 条。固定排序每条工单只需调用一次。 [策略对照](results/strategy-comparison-v1/README.md)
- **开发集分类。** 在 24 条已审核工单上，关键词规则匹配 24 条，模型原顺序匹配 6 条、固定排序匹配 7 条、四次轮换平均匹配 6 条。原顺序和四次轮换平均都把 24 条工单选成了需要澄清。 [开发集评测](results/development-evaluation-v1/README.md)

工单是 AI 构造的开发样例。24 条标签由审核者提供或确认，部分参考了 AI 的解释。编写关键词规则时已接触这些工单，独立测试表现仍待验证。

## 本地运行

已在 Windows x64、Python 3.11 和 CPU 环境验证。安装 Git 和 Python 后执行以下命令。

```powershell
git clone https://github.com/TETU-GAMER/decision-model-lab.git
cd decision-model-lab
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
& '.\.venv\Scripts\python.exe' -X utf8 download_model.py
```

模型下载约 2.32 GB。下载脚本按固定版本获取文件并校验，推理时在本机加载模型，结果写入 `outputs/`。

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 route_ticket.py --strategy single --text 'My parcel was delivered to the wrong address.'
```

四种策略分别是原顺序 `single`、固定排序 `sorted`、四次轮换平均 `cyclic4` 和全排列平均 `all24`，每条工单分别调用 1、1、4 和 24 次。入口默认使用 `cyclic4`，读取 `data/task_policy_v1.json`。每次调用的原始响应都会保存，全部调用成功后才计算平均分数。模型分数尚未校准。

教学例子可以单独运行。加上 `--validate-only` 可只检查输入格式。 [首条模型响应](results/demo-001.json)

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 run_example.py --device cpu
```

## 工单审核与评测

审核工具每次最多显示三条工单，附中文释义。用 `b`、`t`、`d`、`c` 选择账单、技术支持、配送或需要澄清，再输入一句理由保存。标签和理由保存在本机 `local_review/`，该目录由 Git 忽略。

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 review_cases.py
& '.\.venv\Scripts\python.exe' -X utf8 run_evaluation.py --validate-only
& '.\.venv\Scripts\python.exe' -X utf8 run_evaluation.py
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.prompt_ablation
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.prompt_ablation --variant combined
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.two_stage_routing
```

评测需要完整标签，输出准确率、Macro-F1、技术失败数和混淆矩阵。新克隆的仓库需先完成一份本机审核。 [审核与评测说明](docs/REVIEW_AND_EVALUATION.md)

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.order_sensitivity
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.compare_routing_strategies --run-dir results/order-probe-v1
```

## 模型来源

Decision-1.0-Kai-0.6B 由 vLLM Semantic Router 发布。本项目使用固定提交 `ee45160abf994a9eca0e59495bd9b4bf08c1571a`，权重和原始推理代码从 Hugging Face 下载。 [固定版本文件](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/tree/ee45160abf994a9eca0e59495bd9b4bf08c1571a)

模型清单记录文件大小和校验值。来源说明包含许可条款及 Transformers 加载兼容处理。 [模型清单](model-lock.json) | [来源说明](MODEL_PROVENANCE.md)
