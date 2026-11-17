# decision-model-lab

基于现成决策模型的工单路由学习实验：输入一条用户请求和候选部门，返回部门选择及候选概率。

目前已完成本地工单路由、两批共 600 次候选顺序实验，以及四种路由策略的回放对照。尚未训练、微调或开展有独立真值的正式评测。实验代码由 AI 辅助实现；使用者参与需求、技术取舍与结果分析。

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
& '.\.venv\Scripts\python.exe' -X utf8 route_ticket.py --strategy cyclic4 --text 'The approved refund has not appeared in my bank account after ten business days.'
```

支持原样调用 `single`、固定排序 `sorted`、四次轮换平均 `cyclic4`、全排列平均 `all24`，每条新工单分别需要 1、1、4、24 次模型调用。默认 `cyclic4`；执行前显示调用数，结果保留完整子请求。任一子调用失败就停止聚合，不返回部分平均结果。

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

先确定工单的路由规则并人工审核样例，建立独立评测数据；再比较不同策略的分类质量与调用成本。四次轮换后仍会改选的退款、网页空白、缺少包裹三条记录可作为第一批审核材料。是否微调以后再决定。
