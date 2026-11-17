# 路由策略对照 v1

固定日期：2026-11-17。实现、参数与新批次工单在运行对照前提交；方法不按本次结果调整。

## 方法

- `single`：按输入顺序调用一次，作为原有行为。
- `sorted`：按候选 ID 字典序排序后调用一次，作为确定性工程基线。它固定了给模型的输入，顺序不变性不是模型学到的新能力。
- `cyclic4`：保持文字不变，轮换候选起点四次；每个候选各处于每个位置一次。按候选 ID 平均四组概率，再取最大项；平局按 ID 字典序处理。每条新工单需要四次模型调用。
- `all24`：平均全部 24 种排列的概率，作为全排列计算参考。它对外部排列不变是构造性质，不能当作分类正确的证据。

四次轮换只覆盖一个循环群轨道，全部 24 种排列分成六组，因此 `cyclic4` 不保证对任意排列稳定。方法选择基于四个候选的位置平衡与四次调用预算，不进行数据驱动的参数搜索。

## 材料

1. 已有 12 条探索工单：复用 `results/order-probe-v1/` 的全部原始响应，作为已见材料的回放分析。
2. 新的 12 条工单：`data/order_probe_prospective_v1.json`，在本轮推理前固定，不复用之前 15 条文本。仍由 AI 构造，尚未经用户独立审核，没有 gold 标签，不作为正式测试集。

两批材料使用同一指令、部门描述、模型 revision 和 CPU / FP32 设置。新批次仍运行 24 种排列及一次原始排列重复，共 300 次真实模型调用，保留完整响应。

## 比较方法

先取得每条工单的完整 24 种排列响应池，再对每种外部输入排列组合四种策略所需的响应。回放不新增模型调用，不把它描述为逐个策略重复实测的延迟对照。

统计工单改选数、相对原始排列的改选次数、概率 TV 和与全排列均值的选择一致数。后者是参考一致性，不是准确率。部署调用成本分别为 1、1、4、24，单独报告。

源响应池必须完整，错误、重复排列、改动后的输入或错误的重复对照排列都会使分析中止，不静默筛掉样例。重复对照结果另列。

运行后同时保留已见批次和新批次结果。不根据结果替换工单，不把新批次改选数下降写成准确率提升。实际新工单调用入口为 `route_ticket.py`，默认 `cyclic4`，结果含全部原始子请求；子调用失败时不返回部分平均的路由结果。

## 命令

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.order_sensitivity --data data/order_probe_prospective_v1.json
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.compare_routing_strategies --run-dir results/order-probe-v1
& '.\.venv\Scripts\python.exe' -X utf8 -m experiments.compare_routing_strategies --run-dir '<新批次输出目录>'
& '.\.venv\Scripts\python.exe' -X utf8 route_ticket.py --strategy cyclic4 --text 'The approved refund has not appeared in my bank account after ten business days.'
```

本轮不训练或微调，不更换模型，不安装依赖，不接入付费 API，也不扩展为客服平台。
