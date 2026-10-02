# FunASR 工程分析

调研对象：`F:\Codes\iHateVideos\FunASR`，阿里达摩院的语音识别工具箱。包版本 `funasr 1.4.15`（`funasr/version.txt`）。仓库根目录含 `funasr/`、`runtime/`、`examples/`、`docs/`、`model_zoo/`、`tests_models/`、`benchmarks/` 与一份本地中文 `操作手册.md`。

调研方式：只读阅读 `funasr/` 包源码、`docs/`、`model_zoo/`、`examples/`、`runtime/` 的说明文件，并在本机确认解释器、依赖与模型缓存的现状。没有修改 FunASR 仓库与本工程的任何文件，也没有运行过推理。

## 一、它是什么

一个把语音模型、音频前端、模型下载、命令行、服务与部署放在一起的工具箱。推理主入口是 `funasr/auto/auto_model.py` 的 `AutoModel`，只需要一个模型名就能组合出「音频进、带时间戳文本出」的完整链路；训练侧另有 `train.py`、DeepSpeed 与 LoRA 层。

模型权重不随仓库分发，首次使用时按名字从 ModelScope 或 HuggingFace 下载到本地缓存，之后离线可用。同一个仓库里既有 Python 推理实现，也有 `runtime/` 下四套 C++ 运行时（onnxruntime、libtorch、TensorRT、WebSocket），后者用于把模型塞进服务或边缘设备。

## 二、能力清单

| 任务 | 模型与类 | 说明 |
|---|---|---|
| 语音识别 | Paraformer 系列、SenseVoiceSmall、Fun-ASR-Nano、UniASR 系列、Conformer、以及适配的 Whisper / Qwen3-ASR / GLM-ASR-Nano | 离线与流式两条线，流式必须使用带 streaming 的权重 |
| 语音活动检测 | `fsmn-vad`（16k 与 8k）、`silero-vad` | 输出毫秒级语音区间，不做转写，也不判定语句边界与说话人 |
| 标点恢复 | CT-Transformer 系列 | 输出标点编号序列，用于重建句子边界，自身不产生声学时间戳 |
| 说话人 | `cam++`、`ERes2NetV2`、Xvector、SOND、MOSS-Transcribe-Diarize | 声纹向量加聚类给出录音内的说话人编号，编号只在单条录音内有效，不代表已知人物身份 |
| 情感与事件 | SenseVoice 的富标签、`emotion2vec+` | SenseVoice 文本里带 7 类情感与 8 类事件标记（笑声、掌声、背景音等），`emotion2vec+` 是独立的模型与接口 |
| 关键词检测 | FSMN KWS、SANM KWS | 流式实现只在句末返回结果，中间调用返回空 |
| 时间戳 | Paraformer 字级时间戳、SenseVoice 的 CTC 匹配、`fa-zh` 对齐模型、Nano 的 CTC 时间戳 | 各模型的支持程度差别很大，见第六节 |
| 热词 | `paraformer-zh` 的单数 `hotword`、Nano 的复数 `hotwords`、解码后的文本替换 | 文本替换的模糊匹配需要 `pypinyin` 与 `rapidfuzz`，替换后保留原有时间戳 |
| 语音分离 | MossFormer | 多说话人混音分离 |

## 三、模型清单与规模

出自 `model_zoo/modelscope_models_zh.md`、`model_zoo/huggingface_models.md` 与 `README_zh.md`。

| 模型 | 用途 | 参数量 |
|---|---|---|
| Fun-ASR-Nano / Fun-ASR-MLT-Nano | 识别，前者中英日加 7 种方言，后者 31 语种 | 800M |
| SenseVoiceSmall | 识别加情感与事件标签，中英日韩粤 | 234M |
| Paraformer-large（中文、中英、英文版） | 离线识别 | 220M |
| Paraformer（基础、tiny、aishell、aishell2） | 短音频识别 | 68M / 5.2M / 43M / 64M |
| paraformer-zh-streaming | 流式识别 | 220M |
| UniASR 系列 | 流式离线一体化，覆盖十几个语种 | 95M 至 220M |
| Conformer | 识别 | 44M / 220M |
| MFCCA | 多通道多说话人识别 | 45M |
| Whisper-large-v2 / v3 / v3-turbo | 识别与翻译 | 1550M / 1550M / 809M |
| Qwen3-ASR | 识别，52 种语言 | 1.7B |
| GLM-ASR-Nano | 识别，17 种语言 | 1.5B |
| FSMN-VAD（16k / 8k） | 语音活动检测 | 0.4M |
| CT-Transformer-Large / CT-Transformer / 实时版 | 标点恢复 | 1.1G / 291M / 288M |
| cam++ | 说话人向量 | 7.2M |
| Xvector（中文 CNCeleb / 英文 CallHome） | 说话人确认 | 17.5M / 61M |
| SOND（中文 AliMeeting / 英文 CallHome） | 说话人日志 | 40.5M / 12M |
| TP-Aligner（别名 `fa-zh`） | 时间戳预测 | 37.8M |
| emotion2vec+ large / base / seed | 情感识别 | 300M（large） |
| FSMN KWS、SANM KWS | 关键词检测 | 文档未列出 |

## 四、效果数据

### 官方历史评测表

`docs/benchmark/historical_asr.md`：184 条中文长音频，合计 11539 秒，NVIDIA H100 80GB。

| 模型 | 设备 | RTF | 相对速度 | CER |
|---|---|---|---|---|
| SenseVoice-Small | GPU | 0.005896 | 169.6 倍 | 7.81% |
| Paraformer-Large | GPU | 0.008359 | 119.6 倍 | 10.18% |
| Fun-ASR-Nano | GPU | 0.058803 | 17.0 倍 | 8.06% |
| GLM-ASR-Nano | GPU | 0.026974 | 37.1 倍 | 31.07% |
| Whisper-large-v3-turbo | GPU | 0.021708 | 46.1 倍 | 21.71% |
| Whisper-large-v3 | GPU | 0.074694 | 13.4 倍 | 20.02% |
| SenseVoice-Small | CPU | 0.057988 | 17.2 倍 | 7.81% |
| Paraformer-Large | CPU | 0.064056 | 15.6 倍 | 10.18% |
| Fun-ASR-Nano | CPU | 0.274318 | 3.6 倍 | 8.06% |

文档自己把这份表定位为历史记录：原始预测、参考文本与评分程序都不在仓库里，且表里的 11539 秒与 vLLM 表中的 11541 秒不能合并统计。

### vLLM 吞吐

`docs/vllm_guide.md`：同样 184 个文件、11541 秒。Fun-ASR-Nano 在 PyTorch 下的基线是 21 倍实时、CER 8.06%；vLLM 批处理 340 倍、CER 8.20%；离线服务不开说话人 102 倍、CER 8.14%，开说话人 46 倍、CER 8.19%。GLM-ASR-Nano 的 vLLM 为 265 倍、CER 12.93%，文档注明它不支持长音频。

### Fun-ASR-Nano 自带评测

`examples/industrial_data_pretraining/fun_asr_nano/README_zh.md`，WER 百分比：

| 数据集 | Fun-ASR-Nano（0.8B） | Whisper-large-v3（1.6B） | GLM-ASR-Nano（1.5B） |
|---|---|---|---|
| AIShell1 | 1.80 | 4.72 | 1.81 |
| AIShell2 | 2.75 | 4.68 | 3.47 |
| Fleurs-zh | 2.56 | 5.18 | 未列 |
| Fleurs-en | 5.96 | 6.23 | 5.78 |
| Librispeech-clean | 1.76 | 1.86 | 2.00 |
| Librispeech-other | 4.33 | 3.43 | 4.19 |
| WenetSpeech Meeting | 6.60 | 18.39 | 6.73 |
| WenetSpeech Net | 6.01 | 11.89 | 未列 |

工业集平均 WER：Fun-ASR（7.7B）12.70%，Fun-ASR-nano 16.72%，Paraformer v2 23.49%，GLM-ASR-Nano 26.13%，Whisper-large-v3 33.39%；方言项 Nano 28.18% 对 Whisper 66.14%，远场项 5.79% 对 22.21%。这些数字来自模型自带的说明文件，不是第三方复现。

### SenseVoice 自述

`examples/industrial_data_pretraining/sense_voice/README_zh.md` 只给图与文字描述：训练数据 40 万小时以上，宣称支持 50 种以上语言，10 秒音频推理 70 毫秒，比 Whisper-Large 快 15 倍，事件分类效果不如专用模型。文档没有给 CER 数值，checkpoint 实际覆盖的语种是 5 种。

## 五、统一接口 AutoModel

构造参数（`funasr/auto/auto_model.py`、`docs/python_api_zh.md`）：

- `model`：平台别名、完整模型 ID 或本地目录
- `hub`：`ms`（默认）、`hf`、`openai`（专供 Whisper）
- `device`：默认 `cuda`，CPU 需要显式传
- `vad_model`、`punc_model`、`spk_model`：分别配 `vad_kwargs`、`punc_kwargs`、`spk_kwargs`
- `spk_mode`：`punc_segment`（默认）或 `vad_segment`
- 其他：`ngpu`、`ncpu`、`disable_update`、`trust_remote_code`、`model_revision`

输入形式（`prepare_data_iterator`）：本地文件路径、URL、numpy 波形加 `fs=`、`bytes`，以及上述任意组合的列表，还可以传 `.scp`、`.jsonl`、`.txt` 清单。

输出是 `list[dict]`，每个输入一条，常用字段：

| 字段 | 含义 |
|---|---|
| `key` | 输入标识 |
| `text` | 识别文本，可能带模型专属富标签 |
| `timestamp` | `[[起始毫秒, 结束毫秒], ...]`，字或词元级 |
| `sentence_info` | 句级列表，每项含 `start`、`end`（毫秒）、`text`、`sentence`、`timestamp`，配说话人模型时含 `spk` |
| `value` | 单独运行 VAD 时的语音区间 |
| `words` | SenseVoice 走 CTC 时间戳路径时的配对单元 |
| `punc_array` | 标点编号序列（1 无标点，2 逗号，3 句号，4 问号） |

文档记录两条边界：没有语音时 VAD 路径返回空文本与空时间戳，部分分支会直接跳过该条结果，所以不能假定 `results[0]` 一定存在；只配置 `spk_model` 不会给直接推理增加说话人划分，要走长音频入口。

批量参数是 `batch_size`（按条数）与 `batch_size_s`（默认 300 秒）、`batch_size_threshold_s`（默认 60 秒，按片段时长分组）。CPU 设备下 `batch_size` 被强制置为 0，即逐段解码。流式需要 `cache={}` 加 `is_final=True` 与 `chunk_size`，并且权重本身要支持流式。

## 六、长音频的处理流程

配置了 `vad_model` 时 `generate()` 内部走 `inference_with_vad`，步骤固定：

1. 对整条音频跑 VAD，得到毫秒级语音区间，单段时长上限 `max_single_segment_time` 默认 60000 毫秒
2. `merge_vad=True` 时按 `merge_length_s`（默认 15 秒）合并相邻区间
3. 整条音频读成波形，片段按时长排序分组后补齐送入识别模型
4. 把每段结果的时间戳加上该段在整条音频里的起始时刻
5. 配置标点模型时对拼接文本跑标点，用标点编号重建句子边界
6. `sentence_timestamp=True` 时写出 `sentence_info`
7. 配置声纹模型时对每段取声纹向量，整体聚类后把编号写进 `sentence_info[].spk`

时间戳能力按模型差别很大，这是选型的关键：

- **Paraformer** 的字级时间戳由权重直接给出，文档把它作为默认推荐路径，是三者中最省事的
- **SenseVoice-Small** 默认 `output_timestamp=False`，不返回时间戳；要显式打开才走 CTC 匹配，返回 `words` 与毫秒 `timestamp` 两个平行列表。文档里的实测记录：1.4.15 版本上中文样例带 ITN 得到 242 个配对单元、不带 217 个，英文样例 84 个显示字符只对应 16 个配对单元
- **Fun-ASR-Nano** 的字符级时间戳要求 checkpoint 同时含 `ctc_decoder.*` 与 `ctc.*` 权重，`Fun-ASR-MLT-Nano` 没有这些权重，只返回文本并给出警告；历史评测表也标注它的原生时间戳不可靠
- **`fa-zh`** 是独立的时间戳模型，需要音频与文本成对输入，不能单独使用

文档另有一条通用提醒：经过标点与文本规整之后，时间戳与显示字符不一定一一对应。

## 七、命令行与服务

命令行 `funasr`（`funasr/cli.py`，四个别名 `sensevoice`、`paraformer`、`paraformer-en`、`fun-asr-nano`）：

```bash
funasr audio.wav --timestamps -f json -o ./results
funasr audio.wav -f srt -o ./subs
funasr meeting.wav --model paraformer --spk --timestamps -f json -o ./meetings
```

`-f` 支持 `json`、`srt`、`tsv` 等；SRT 默认按「间隔不超过 500 毫秒、合并后不超过 8 秒、文字不超过 42 字、不跨说话人变化」分组。与工程习惯不同的三点：位置参数不接受音频 URL；`--timestamps` 只保留模型已经返回的时间戳，不额外请求；同名输出会被覆盖，没有断点续跑。

服务与部署：`funasr-server`（`funasr/bin/server.py`）、实时 WebSocket 服务（`funasr/bin/realtime_ws.py`）、`examples/openai_api/` 的 OpenAI 兼容示例；`runtime/` 下四套 C++ 运行时有独立的构建说明，Windows 需要 Visual Studio 打开对应的解决方案，另有 GGUF 边缘包（Windows x64 的 CUDA 与 Vulkan 包），但 GGUF 权重不能作为 `AutoModel` 的输入。

现成可跑的示例：`examples/subtitle/generate_subtitle.py`（音视频转 SRT 或 VTT，支持 `--spk`、`--segment-mode`、`--max-single-segment-time`）、`examples/batch_asr_improved.py`（目录批量转文本）、`examples/migration/benchmark_funasr.py`（批量评测并写逐文件计时）、`tests_models/test_sensevoice.py`（最小推理脚本）。

## 八、依赖与安装要求

`setup.py` 的 `install_requires` 不含 `torch`、`torchaudio`、`onnxruntime`，这三个必须自行安装，文档里明确说明核心包不会替使用者选择 torch 的构建版本。必装的核心依赖包括 `modelscope`、`huggingface_hub`、`transformers`、`safetensors`、`librosa`、`soundfile`、`numpy`、`scipy`、`omegaconf`、`hydra-core`、`kaldiio`、`jieba`、`rapidfuzz`、`sentencepiece`、`tiktoken`、`oss2`、`websockets` 等。可选 extras 有三个：`knf`（torchaudio 缺失时的特征后端）、`silero`、`all`。

`python_requires` 是 `>=3.7.0`，分类器写到 3.12，安装文档的示例统一用 Python 3.11。`README_zh.md` 要求 PyTorch 1.13 以上并同时安装 torchaudio。音频解码优先调用 `ffmpeg`（需在 PATH 中），缺失时回退 torchaudio。

`funasr/` 包内部没有任何平台判断代码，官方给了 Windows 的建虚拟环境步骤。模型下载默认走 ModelScope，缓存位置由库的默认值决定（`~/.cache/modelscope`，可用 `MODELSCOPE_CACHE` 改写），切到 HuggingFace 时用 `HF_HUB_CACHE`。

## 九、本机现状

都是实测结果：

- `F:\Codes\iHateVideos\FunASR\.venv` 是 uv 建的 Python 3.11.4（基础解释器来自 `E:\Anaconda`），已装 `funasr 1.4.15`、`modelscope 1.40.0`、`transformers 5.17.0`、`numpy 2.4.6`、`librosa 0.11.0`、`oss2` 等，**没有 torch 与 torchaudio**（`import torch` 报 `ModuleNotFoundError`），现在跑不了推理
- `~/.cache/modelscope` 为空（`models` 与 `hub` 两层都没有内容），没有下载过任何 FunASR 权重
- `~/.cache/huggingface/hub` 里只有图像模型，与 FunASR 无关
- `E:\Anaconda\python.exe` 带 `torch 2.5.1+cu121` 与 `torchaudio 2.5.1+cu121`，`torch.cuda.is_available()` 为 `True`，设备名是 `NVIDIA GeForce RTX 4080 SUPER`；同环境还有 `transformers 4.57.6`、`modelscope 1.37.0`、`onnxruntime-gpu 1.29.0`
- 系统 Python 3.11 里的 `torch 2.7.1+cpu` 是 CPU 版，跑不了 GPU 推理
- `nvidia-smi` 报驱动 591.86、CUDA 13.1，单卡可用显存 32760 MiB

## 十、与本工程的结合点

本工程当前没有语音识别实现：`export/json_to_md.py` 只接受工程外部产出的转录 JSON，`docs/cloud-stt.md` 是云端选型调研，没有对应代码。已有的两条链路可以直接接上 FunASR：

- `media` 模块的 `audio` 子命令已经能提取 16 kHz 单声道音轨并按时长分块，这正是识别模型的标准输入
- `export/json_to_md.py` 认两种带时间的载荷：`segments[]`（每项 `start` 秒与 `text`）与 `transcripts[].sentences[]`（每项 `begin_time` 毫秒、`text`、可选 `speaker_id`）。FunASR 的 `sentence_info`（`start` 与 `end` 毫秒、`text`、`spk`）转换到这两种结构是一层直接映射

调用方式上，FunASR 是普通的 pip 包，可以只当库使用，不必使用整个仓库：

```python
from funasr import AutoModel

model = AutoModel(
    model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc",
    device="cuda",
)
res = model.generate(input="audio.wav", batch_size_s=60, sentence_timestamp=True)
for sent in res[0]["sentence_info"]:
    print(sent["start"], sent["end"], sent["text"])
```

按本工程的音频特征（中文长音频为主、来源多为播客与讲解视频），可以走的三条路：

| 侧重 | 组合 | 取舍 |
|---|---|---|
| 时间戳稳定 | `paraformer-zh` + `fsmn-vad` + `ct-punc` | 字级时间戳由权重给出，句边界靠标点，中文 CER 10.18% |
| 速度与准确率 | `SenseVoice-Small` + `fsmn-vad`，开 `output_timestamp=True` | 中文 CER 7.81%、GPU 169.6 倍，时间戳来自 CTC 匹配，配对单元与显示字符不一一对应 |
| 只要文本的高准确率 | `Fun-ASR-Nano` | WER 明显低于 Whisper 系列，checkpoint 原生时间戳不可靠 |

可选加 `cam++` 拿到录音内的说话人编号。

## 十一、需要决定的事项

1. 本地方案与云端方案的关系：只做本地、只做云端，还是像 `docs/cloud-stt.md` 设想的那样留一套适配器接口，两条路共用输出结构
2. 模型组合：按上一节的三个侧重选一个作为默认，其余作为可选参数
3. 运行环境：给工程加一个带 CUDA 版 torch 的环境（`install_requires` 不含 torch，必须显式安装），还是复用 `E:\Anaconda` 的解释器；torch 版本要与 transformers 协调
4. 权重存放与下载策略：权重放工程外的默认缓存目录，还是放在可配置的目录；首次使用的联网下载如何提示
5. 长音频策略：依赖 FunASR 内部的 VAD 分段，还是先用 `media` 分块再逐块识别并拼接时间戳（后者可以复用工程已有的分块产物与并行能力，代价是自己维护时间偏移）
