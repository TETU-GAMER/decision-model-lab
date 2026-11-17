# 模型来源与使用范围

本仓库是使用公开模型的独立学习实验，提供下载校验、工单输入和结果保存代码，不宣称创建或改进了上游基础模型。

## 固定来源

- 发布者：The vLLM Semantic Router Authors / Hugging Face `vllm-sr`。
- 模型 ID：`vllm-sr/Decision-1.0-Kai-0.6B`。
- 固定 revision：`ee45160abf994a9eca0e59495bd9b4bf08c1571a`。
- [固定版本模型卡](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/blob/ee45160abf994a9eca0e59495bd9b4bf08c1571a/README.md)。
- [固定版本文件树](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/tree/ee45160abf994a9eca0e59495bd9b4bf08c1571a)。
- 文件清单与摘要：[model-lock.json](model-lock.json)。

本实验使用 `vela-encoder` 推理分支，接口为 Transformers `AutoModel` 与自定义的 `system_one`。模型参数、分词器及上游 Python 模块由下载脚本从固定提交获取，不随本仓库重新分发。

## 许可与归属

上游 Decision 贡献及文档采用 Apache-2.0；保留的 Vela/mmBERT 材料和 Gemma 来源分词器另有适用条款。Apache-2.0 标签不替代第三方条款。完整范围以固定版本原始文件为准：

- [LICENSE](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/blob/ee45160abf994a9eca0e59495bd9b4bf08c1571a/LICENSE)
- [NOTICE](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/blob/ee45160abf994a9eca0e59495bd9b4bf08c1571a/NOTICE)
- [许可范围](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/blob/ee45160abf994a9eca0e59495bd9b4bf08c1571a/LICENSING_STATUS.md)
- [分发条款](https://huggingface.co/vllm-sr/Decision-1.0-Kai-0.6B/blob/ee45160abf994a9eca0e59495bd9b4bf08c1571a/DISTRIBUTION_TERMS.md)

下载清单保留上游许可证、NOTICE、分词器条款及来源文件。这些模型来源和许可不归属于本实验作者。

## 本项目的兼容处理

首次运行采用 Python 3.11.9、PyTorch 2.6.0+cpu、Transformers 4.57.6、safetensors 0.6.2、huggingface_hub 0.36.0，完整依赖见 `requirements-lock.txt`。

Transformers 4.57.6 从本地目录加载时仅复制直接相对导入，递归扫描会因间接依赖 `decision1_rocm_conv.py` 尚未进入模块缓存而失败。该文件本身已下载。实验入口先把全部七个已核对摘要的源文件加入项目内加载缓存，再调用原接口。上游源文件和权重未改动，也没有因此安装或执行 ROCm/Triton。

本机保留首次失败及修复后的成功日志。共享的 `results/demo-001.json` 是修复后真实调用的导出，完整保留请求和模型响应，仅移除了本机绝对路径。

## 已验证范围

已验证单条工单推理、两批候选顺序探索，以及四次轮换平均的调用入口，均使用 CPU / FP32。具体请求、响应及来源摘要见 `results/`。策略对照由完整响应池回放计算，不等同于各策略端到端延迟实测。

没有训练、微调、GPU 实测或独立标注的准确率评测。模型发布配置使用原始概率，聚合后的概率也没有校准。顺序稳定不代表分类正确；固定排序及全排列平均的顺序不变性属于构造性质。

2026-11-18 另完成了 24 条用户给出或确认标签的开发集分类对照，包含 AI 辅助审核；它不是独立测试结果。该轮固定任务规则、模型和方法，保存 144 次真实模型调用，并核查了评分及标签隔离。具体来源和结果见 `results/development-evaluation-v1/`。
