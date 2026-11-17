# decision-model-lab

基于现成决策模型的工单路由学习实验：输入一条用户请求和候选部门，返回部门选择及候选概率。

目前已完成单条教学推理，以及 12 条新探索工单的候选顺序实验，共保存 300 次实验调用。尚未训练、微调或开展有独立真值的正式评测。实验代码由 AI 辅助实现；使用者参与需求、技术取舍与结果分析，独立掌握程度另行记录。

## 模型来源与版本

- 发布者：vLLM Semantic Router（Hugging Face 账号 `vllm-sr`）。
- 模型：[Decision-1.0-Kai-0.6B](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B)。
- 固定提交：`ee45160abf994a9eca0e59495bd9b4bf08c1571a`。
- [固定版本的模型卡与推理代码](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/tree/ee45160abf994a9eca0e59495bd9b4bf08c1571a)。
- 本仓库提供独立实验入口，模型来自上游；上游模型代码和权重未修改。

下载清单、大小和已固定的 SHA256 见 [model-lock.json](model-lock.json)。模型来源、许可范围和加载兼容处理见 [MODEL_PROVENANCE.md](MODEL_PROVENANCE.md)。

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

先由使用者阅读并审核一条发生改选的工单，说明合理的部门及信息不足时的处理规则。然后审核更多样例、建立独立评测数据；再决定是否比较规则、普通 LLM 和决策模型，或研究缓解顺序影响的方法。是否微调以后再决定。
