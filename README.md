# decision-model-lab

基于现成决策模型的工单路由学习实验：输入一条用户请求和候选部门，返回部门选择及候选概率。

目前已完成本地工单路由、两批共 600 次候选顺序实验、四种路由策略的回放对照，以及 24 条用户确认标签的首次开发集分类评测。尚无独立测试结果，没有训练或微调。实验代码由 AI 辅助实现；使用者参与需求、技术取舍、标注和结果分析。

## 首次开发集分类结果

2026-11-18，24 条工单完成审核后，使用已固定的 `ticket-routing-v1` 规则运行对照：

- 关键词规则：匹配 24/24，准确率 100%。
- 原样调用：匹配 6/24，准确率 25%。
- 固定排序：匹配 7/24，准确率 29.17%。
- 四次轮换平均：匹配 6/24，准确率 25%。

共完成 144 次模型调用，技术失败为 0。模型在当前指令下几乎全选需要澄清；顺序稳定没有转化成分类质量提升。规则基线的全匹配也只限于这批已见、关键词明显的开发材料。

标签包含 AI 辅助确认，样例也已用于开发，因此这些分数不是独立测试结果。[完整结果与来源](results/development-evaluation-v1/README.md)保留了预测、环境、混淆矩阵和核对记录，原始人工标注及理由仍在本机。

## 任务规则与人工审核

当前采用 `ticket-routing-v1`：**明确主要诉求优先分配；多个独立问题同等重要且没有明确主次时，选择需要澄清。** 规则已接入默认路由指令，旧实验及其原始指令保持原样。

已补上 24 条开发工单的审核队列、英文关键词规则基线和评测脚本。默认每次最多审核 3 条，提供中文参考释义，不展示模型预测：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 review_cases.py
```

按 `b`、`t`、`d`、`c` 选择账单、技术支持、配送、需要澄清，并填写一句理由。每条完成即保存，下次继续。人工标注保存在被 Git 排除的 `local_review/` 中。

[审核和评测说明](docs/REVIEW_AND_EVALUATION.md)列出了完整命令。标签补齐前不进行评分；补齐后可比较规则和模型方法的准确率、Macro-F1 及失败率。这些旧探索样例审核后仍属于开发材料。

新规则的一次真实调用暴露了失败：“重复扣款，请先解决登录问题”仍被模型分到需要澄清。[原始记录](results/task-policy-v1/README.md)保留了新指令、响应和当时的审核进度。现已完成全部 24 条审核并生成上方开发集对照，29 项离线检查通过。

## 模型来源与版本

- 发布者：vLLM Semantic Router（Hugging Face 账号 `vllm-sr`）。
- 模型：[Decision-1.0-Kai-0.6B](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B)。
- 固定提交：`ee45160abf994a9eca0e59495bd9b4bf08c1571a`。
- [固定版本的模型卡与推理代码](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/tree/ee45160abf994a9eca0e59495bd9b4bf08c1571a)。
- 本仓库提供独立实验入口，模型来自上游；上游模型代码和权重未修改。

下载清单、大小和已固定的 SHA256 见 [model-lock.json](model-lock.json)。模型来源、许可范围和加载兼容处理见 [MODEL_PROVENANCE.md](MODEL_PROVENANCE.md)。

## 路由入口与策略对照

在完成下方的环境准备及模型下载后，可直接输入工单：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 route_ticket.py --strategy cyclic4 --text 'My card was charged twice. Please fix my login first.'
```

支持原样调用 `single`、固定排序 `sorted`、四次轮换平均 `cyclic4`、全排列平均 `all24`，每条新工单分别需要 1、1、4、24 次模型调用。默认 `cyclic4`；执行前显示调用数，结果保留完整子请求。任一子调用失败就停止聚合，不返回部分平均结果。

默认任务指令来自 `data/task_policy_v1.json`。复现早期教学指令的路由示例时，加上 `--legacy-demo-config`；输出会记录实际规则 ID 和配置摘要。

两批探索材料的回放对照中，四次轮换平均使发生改选的工单数从旧批次的 7/12 降到 1/12，新批次从 6/12 降到 2/12。固定排序只调用一次，两批均不随外部排列改选；这来自输入被固定。当前只比较顺序稳定性，尚不能判断谁更准确。

[策略实现、完整对照结果与剩余问题](results/strategy-comparison-v1/README.md)记录了调用成本、仍会改选的工单，以及四次调用入口的实际输出。完整新批次原始响应也已保存。两批各有 300 次真实调用；策略比较复用这些响应，不把回放计算计作新增推理。

离线检查与回放命令：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.compare_routing_strategies --run-dir results/order-probe-v1
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.compare_routing_strategies --run-dir results/order-probe-prospective-v1
```

16 项检查覆盖统计、概率聚合、异常处理和顺序不变性的边界。[本轮固定协议](experiments/STRATEGY_COMPARISON_V1.md)包含方法定义和复现步骤。

## 候选顺序敏感性实验 v1

2026-11-17，对 12 条 AI 构造的新英文探索工单枚举全部 24 种候选排列，再各重复一次原始排列，共 300 次 CPU 推理，全部调用有效。

- **7/12 条工单**的部门选择随排列发生变化。
- 相对原始排列，276 次非原始排列比较中有 **47 次**选择变化（约 17.03%）。
- 12 组原始排列重复对照的选择与概率均完全复现。

这说明该固定模型在本批样例下存在候选顺序敏感性；不是错误率或准确率结论，也不能推广为真实工单的变化比例。没有 gold 标签，场景标签不传给模型；原始三条教学例未复用。所有数据和结果均保留，未筛掉失败或只展示发生变化的工单。

例如“退款十个工作日仍未到账”，仅改变候选排列，模型就在账单与需要澄清之间改选。具体请求对见[结果说明](results/order-probe-v1/README.md)，完整 300 条请求与响应、数据快照、环境及摘要均可查看。

运行前固定的[实验协议](experiments/ORDER_PROBE_V1.md)和[实验脚本](experiments/order_sensitivity.py)已提交。复现命令（先完成下方环境准备与模型下载）：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.order_sensitivity --validate-only
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.order_sensitivity
```

七项离线检查覆盖概率 ID 对齐、重复对照分离、失败分母、重复编号和输入边界。每次实验写入新的 `outputs/order-probe-*` 目录，不覆盖既有结果。

## 首条实际结果

2026-11-16（Asia/Shanghai），在 Windows x64 / Python 3.11.9 / CPU / FP32 环境运行 `demo-001`。

> I was charged twice for the same order. Please check the duplicate charge.

即“同一订单被重复扣款，请检查”。模型选择 **billing（账单）**：

- billing：0.8422572612762451
- technical：0.01825552247464657
- delivery：0.012157524935901165
- needs_clarification：0.12732969224452972

[完整请求与模型响应](results/demo-001.json)保留实际版本、设备和单次耗时；导出时仅移除了本机绝对路径，原始本机记录另行保留。该次加载约 4.67 秒、推理约 0.210 秒，不含下载时间，也不是速度基准。

`examples.json` 中三条记录均为人工构造的教学示例，`intended_choice` 只表达设计意图，不是独立审核的测试标签，也不会传给模型。候选概率未经本项目校准；响应中的 `confidence` 是前两名概率之差，不能当成实际正确率。

## 复现

已验证平台是 **Windows x64、Python 3.11、CPU**。依赖文件中的 PyTorch wheel 专用于此平台，其他系统和 GPU 推理尚未验证。

先安装 Git 和 Python 3.11，在终端执行：

```powershell
git clone https://github.com/TETU-GAMER/decision-model-lab.git
cd decision-model-lab
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
```

检查输入结构（不联网、不加载模型）：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 run_example.py --validate-only
```

下载固定版本并校验（约 2.32 GB，不执行模型自定义代码）：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 download_model.py
```

随后从本地离线加载并运行第一条：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 run_example.py --device cpu
```

下载步骤访问 Hugging Face；推理步骤设置离线模式，使用原始 `system_one(state=..., questions=...)` 接口。脚本在执行前校验七个已审阅 Python 模块的 SHA256，并使用模型所需的 `trust_remote_code=True`。完整新响应保存到 `outputs/`。

模型文件在 `models/`，环境在 `.venv/`，缓存位于 `.cache/`，均不上传到 GitHub。本机审阅快照和运行日志留在 `audit/`，下载校验记录也会在此目录生成。

## 下一步

先定位当前模型为何过度选择需要澄清：用受控对照检查指令和候选描述，再决定下一轮改动。后续另建未参与开发的评测材料；是否微调以后再决定。
