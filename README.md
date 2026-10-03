# 创作者工作流

这个仓库用于沉淀可复用的创作、语音转文字与后续分析工作流。当前最需要稳定化的是 **语音转文字（ASR）链路**：仓库已经有转写脚本、VAD 路径、Whisper 模型下载 workflow 和 whisper.cpp 便携构建 workflow，但这些组件目前仍是分散的，尚未形成“原始媒体输入 → 自动准备运行时 → VAD/转写 → 可复用逐字稿”的单一入口。

> 本 README 只描述仓库当前真实能力，以及下一步应该如何稳定串联。未实现的能力会明确标为“目标结构”，不会写成已经完成。

## 当前状态

截至 2026-10-03（新增端到端 smoke CI；首次实际运行结果以 Actions 为准）：

| 日期 | 变更 | 当前状态 |
| --- | --- | --- |
| 2026-09-20 | 新增 `.github/workflows/fetch-whisper-small-q5.yml` | 可手动或在该 YAML 变更时运行；下载 `ggml-small-q5_1.bin`，Artifact 保留 1 天 |
| 2026-09-21 | 新增 `.github/workflows/build-whisper-portable.yml` | 可手动或在该 YAML 变更时运行；构建 whisper.cpp 1.7.6 的 Linux x64 `whisper-cli`，Artifact 保留 1 天 |
| 2026-09-22 | 更新根目录 `README.md` | 当时仅保留“创作者工作流”标题 |
| 当前 | `语音转文字/` 已包含 Skill、runtime lock、bootstrap、whisper.cpp 转写 wrapper 和 smoke test | 可以在运行时资产已经准备好的前提下执行 whisper.cpp 转写 |
| 2026-10-03 | 新增 `.github/workflows/asr-smoke.yml` | 按 runtime lock 构建 CLI、下载 base Q5、生成短语音并执行实际转写，验证 TXT/SRT/JSON/manifest；结果与失败日志保留 14 天 |
| 当前 | 根目录 `scripts/transcribe_audio.py` + `scripts/ensure_runtime.sh` | 另一条独立的 `faster-whisper` 转写路径，已开启 VAD |

原有两个 GitHub Actions 仍然都是 **独立的临时 bootstrap 任务**，不是端到端转写任务。它们之间没有 `needs` 依赖，也不会自动调用仓库里的转写脚本。

另外，因为原有两个 workflow 的 `push.paths` 都只监听各自 YAML 文件，所以 **只修改 README、Skill 或转写脚本不会触发这两个 workflow**。

---

## 仓库里目前有两条 ASR 路径

### 1. whisper.cpp 路径：当前 Skill 主线

主要文件：

- `语音转文字/SKILL.md`
- `语音转文字/runtime/runtime-lock.json`
- `语音转文字/scripts/bootstrap_from_session_assets.sh`
- `语音转文字/scripts/transcribe_media.py`
- `语音转文字/tests/smoke_test.sh`

这条路径会：

1. 接收任何 FFmpeg 可解码的音频/视频；
2. 标准化为 16 kHz 单声道 WAV；
3. 查找 `whisper-cli`；
4. 查找 base 或 small Q5 模型；
5. 执行 whisper.cpp；
6. 输出 TXT / SRT / JSON；
7. 生成带源文件 SHA-256 的 ASR manifest，供后续复用。

**当前缺口：这条路径还没有独立 VAD 阶段。**

### 2. faster-whisper 路径：当前已有 VAD

主要文件：

- `scripts/ensure_runtime.sh`
- `scripts/transcribe_audio.py`

这条路径会安装/复用 `faster-whisper==1.2.1`，并使用：

- `vad_filter=True`
- `min_silence_duration_ms=500`
- `speech_pad_ms=250`
- word timestamps
- checkpoint / resume 输出

它已经包含 VAD，但目前与 `语音转文字/` 下的 whisper.cpp runtime、GitHub Actions 模型 Artifact 和便携 CLI Artifact **没有自动桥接**。

长期应收敛为一个统一入口，而不是让调用方自己判断该走哪条链路。

---

## 原有 bootstrap 与统一入口仍待解决的接口错位

新增 `asr-smoke.yml` 已在 CI 内按 lock 准备 CLI/base 模型并写入固定 runtime 路径；以下旧 bootstrap 的版本、压缩包与 small 模型问题仍然存在。本次没有修改它们，也没有实现通用资产桥接或 VAD。

### 1. 默认全程转写需要 base，但模型 workflow 只产 small

`语音转文字/scripts/transcribe_media.py` 默认：

```text
--strength base
→ ggml-base-q5_1.bin
```

small 主要用于关键片段精转：

```text
--strength small
→ ggml-small-q5_1.bin
```

但当前 `fetch-whisper-small-q5.yml` 只下载：

```text
ggml-small-q5_1.bin
```

因此这个 workflow 的产物不能单独满足默认的完整长音频转写链路。

### 2. build workflow 的 Artifact 结构与 bootstrap 期待结构不一致

当前构建 workflow 上传的是一个裸文件：

```text
artifact: whisper-cpp-176-portable-linux
└── whisper-cli
```

而 `bootstrap_from_session_assets.sh` 当前优先识别的是：

```text
/mnt/data/whisper-bin-ubuntu-x64-artifact.zip
└── whisper-bin-ubuntu-x64.tar.gz
    └── whisper-bin-ubuntu-x64/
        └── whisper-cli
```

所以即使 GitHub Actions 已成功构建 `whisper-cli`，现有 bootstrap 也不能直接消费这个 Artifact。

### 3. 模型 Artifact 与 bootstrap 命名同样没有对齐

当前模型 workflow Artifact 内是裸文件：

```text
ggml-small-q5_1.bin
```

而 bootstrap 当前还会查找：

```text
/mnt/data/whisper-small-q5_1.zip
```

这意味着“模型已经下载成功”和“本地 runtime 已经能自动识别模型”目前仍是两件事。

### 4. whisper.cpp 版本没有统一

当前临时构建 workflow 固定：

```text
whisper.cpp v1.7.6
```

但：

```text
语音转文字/runtime/runtime-lock.json
```

记录的 tested runtime 是：

```text
whisper.cpp 1.9.2
```

稳定化前必须二选一：

- 把 build workflow 升到 runtime lock 的版本；
- 或把 runtime lock 回退到实际要长期支持的版本。

不应长期维持“两套版本都像正式标准”的状态。

### 5. Artifact 只保留 1 天

两个临时 workflow 都使用：

```yaml
retention-days: 1
```

因此它们适合作为 **临时桥接 / 恢复手段**，不适合作为长期运行时分发机制。

稳定链路应优先：

1. 复用本地缓存；
2. 直接从固定来源下载并校验；
3. 使用版本化 Release / 长期可取资产；
4. GitHub Actions Artifact 仅作为网络受限时的短期桥梁。

---

## 最小可复用目录结构

下面是与当前脚本兼容的最小结构。二进制和模型属于运行时资产，**不建议提交进 Git**。

```text
.
├── README.md
├── .github/
│   └── workflows/
│       ├── build-whisper-portable.yml      # 临时：构建 Linux x64 whisper-cli
│       ├── fetch-whisper-small-q5.yml       # 临时：下载 small Q5
│       └── asr-smoke.yml                   # 端到端短语音转写 CI
│
├── 语音转文字/
│   ├── README.md
│   ├── SKILL.md
│   ├── runtime/
│   │   ├── runtime-lock.json                # 版本、模型与来源的单一事实源
│   │   ├── whisper-bin-ubuntu-x64/          # 本地生成/解压，不提交 Git
│   │   │   └── whisper-cli
│   │   ├── ggml-base-q5_1.bin               # 全程转写默认模型，不提交 Git
│   │   └── ggml-small-q5_1.bin              # 关键片段精转模型，不提交 Git
│   ├── scripts/
│   │   ├── bootstrap_from_session_assets.sh
│   │   ├── transcribe_media.py
│   │   └── refine_segment.py
│   └── tests/
│       ├── smoke_test.sh                   # 保留原有文件/--help 检查
│       ├── e2e_smoke_test.sh               # 生成语音并调用现有 wrapper
│       └── verify_smoke_outputs.py         # 检查产物内容、时间轴与 manifest
│
└── scripts/
    ├── ensure_runtime.sh                     # faster-whisper runtime
    ├── transcribe_audio.py                   # 当前 VAD 路径
    ├── inspect_media.py
    └── finalize_transcript.py
```

对于 whisper.cpp 路径，调用方最终只应该依赖三个稳定位置：

```text
语音转文字/runtime/whisper-bin-ubuntu-x64/whisper-cli
语音转文字/runtime/ggml-base-q5_1.bin
语音转文字/runtime/ggml-small-q5_1.bin
```

任何 GitHub Artifact、`/mnt/data` 临时文件、下载缓存或压缩包，都应该由“桥接层”归一化到这些路径，再交给转写脚本。

---

## 依赖关系

### 基础依赖

| 组件 | 作用 | 是否必需 |
| --- | --- | --- |
| FFmpeg | 解码任意媒体、抽取音轨、转 16 kHz mono WAV | 必需 |
| Python 3 | 调用 wrapper、manifest、faster-whisper 路径 | 必需 |
| `whisper-cli` | whisper.cpp 实际推理 | whisper.cpp 路径必需 |
| `ggml-base-q5_1.bin` | 长音频完整时间轴默认模型 | whisper.cpp 默认主线必需 |
| `ggml-small-q5_1.bin` | 关键商业节点/疑难片段二次精转 | 建议 |
| `faster-whisper==1.2.1` | 当前已有 VAD 的备用/并行 ASR 路径 | faster-whisper 路径必需 |

### 运行依赖图

```text
原始音频 / 视频
        │
        ▼
   媒体检查 / FFmpeg
        │
        ├──────────────► VAD
        │                  │
        │                  └─ 当前实现：faster-whisper 路径已有
        │
        ▼
运行时解析
        │
        ├─ 本地已有 whisper-cli ─────────────┐
        │                                     │
        ├─ session/cache 已有 CLI ────────────┤
        │                                     │
        └─ GitHub Actions / 本地构建 CLI ─────┤
                                              ▼
模型解析                                  统一桥接层
        │                                     │
        ├─ 本地已有 base/small ───────────────┤
        │                                     │
        ├─ session/cache 已有模型 ────────────┤
        │                                     │
        └─ 直接下载 / Actions Artifact ───────┘
                                              │
                                              ▼
                                      runtime smoke test
                                              │
                                              ▼
                                        完整 ASR
                                              │
                              ┌───────────────┴───────────────┐
                              ▼                               ▼
                        全程 base pass                  关键 small pass
                              │                               │
                              └───────────────┬───────────────┘
                                              ▼
                                   transcript QA + manifest
                                              │
                                              ▼
                              总结 / Call 分析 / 情绪分析
```

---

## 稳定执行顺序

后续无论手机、电脑还是云端环境，都应遵循同一个顺序，避免“先跑到哪算哪”。

### 第 0 步：只接收原始媒体

用户提供原始录音或视频即可。

不要求用户先：

- 转 WAV；
- 自己生成逐字稿；
- 自己下载模型；
- 自己判断 Whisper 引擎；
- 自己拆分音频。

### 第 1 步：检查媒体

确认：

- 文件存在；
- FFmpeg 能解码；
- 时长合理；
- 原始媒体保持不变。

### 第 2 步：标准化音频

统一为：

```bash
ffmpeg -y -i INPUT -vn -ac 1 -ar 16000 -c:a pcm_s16le OUTPUT.wav
```

### 第 3 步：VAD

目标是先识别有效语音区间，减少长静音对 ASR 的干扰。

当前状态：

- `scripts/transcribe_audio.py` 已集成 faster-whisper VAD；
- `语音转文字/scripts/transcribe_media.py` 尚未集成单独 VAD。

因此 **当前不能把“whisper.cpp 主线已包含 VAD”写成既成事实**。

长期稳定版本应把 VAD 作为统一入口中的固定阶段，而不是散落在其中一条备用转写路径里。

### 第 4 步：解析 / 准备 whisper runtime

固定优先级：

1. 已存在可执行的本地 `whisper-cli`；
2. 已存在 session / cache 资产；
3. 已下载的版本化二进制；
4. GitHub Actions Artifact 桥接；
5. 最后才本地构建。

准备完成后必须执行：

```bash
whisper-cli --help
```

### 第 5 步：解析 / 准备模型

完整长音频优先：

```text
ggml-base-q5_1.bin
```

关键节点精转：

```text
ggml-small-q5_1.bin
```

模型必须先进入稳定 runtime 路径，再运行转写。

### 第 6 步：桥接运行时资产

“桥接”是当前最缺的一层。

无论上游资产来自：

- GitHub Actions Artifact；
- `/mnt/data`；
- 直接下载；
- 本地构建；
- 历史 session cache；

都应该统一落到：

```text
语音转文字/runtime/whisper-bin-ubuntu-x64/whisper-cli
语音转文字/runtime/ggml-base-q5_1.bin
语音转文字/runtime/ggml-small-q5_1.bin
```

然后再由 `transcribe_media.py` 读取。

调用方不应该自己理解 Artifact 的内部压缩结构。

### 第 7 步：smoke test

在正式转录前，至少验证：

```bash
bash 语音转文字/tests/smoke_test.sh
```

`smoke_test.sh` 仍只检查文件与 `--help`，需要 **base Q5 模型**。完整短语音测试另由 `e2e_smoke_test.sh` 执行；运行方法见下面的端到端 smoke CI 章节。旧检查直接调用 bootstrap；因仓库记录的权限为 0644，CI 会先执行 `chmod +x 语音转文字/scripts/bootstrap_from_session_assets.sh`。

### 第 8 步：完整时间轴转写

推荐主入口：

```bash
python3 语音转文字/scripts/transcribe_media.py \
  "/path/to/input.m4a" \
  --output-dir "/path/to/output" \
  --strength base \
  --language zh
```

预期产物包括：

```text
<stem>.transcript.txt
<stem>.asr-base.txt
<stem>.asr-base.srt
<stem>.asr-base.json
<stem>.normalized-16k.wav
<stem>.asr-manifest.json
```

manifest 中保存源文件 SHA-256，后续应优先复用已有结果。

### 第 9 步：关键片段 small 精转

对以下片段建议使用 `small q5_1` 二次确认：

- 价格 / 预算；
- 分期 / 首付；
- “考虑一下”；
- 竞品比较；
- 明确承诺或退出；
- 退款机制；
- 最后 3–8 分钟；
- 任何会决定成交/丢单因果链的片段。

### 第 10 步：质检后再进入下游分析

至少检查：

- 是否覆盖到录音结尾；
- 首尾有效语音是否存在；
- 是否出现重复循环 / 幻觉；
- 关键报价、数字、专有名词；
- 关键引用是否经过 small 模型或音频复核。

只有完成这一层，才进入总结、Call 分析、情绪分析或报告生成。

---

## 临时 workflow：现在保留什么，之后删除什么

### 现在：两个都先保留

当前建议 **暂时不要删除**：

```text
.github/workflows/build-whisper-portable.yml
.github/workflows/fetch-whisper-small-q5.yml
```

原因不是它们已经构成正式链路，而是它们目前仍是已验证可用的：

- Linux x64 CLI 临时构建入口；
- small Q5 模型临时下载桥梁；
- 网络受限时的恢复手段。

在统一链路真正跑通前删掉，会失去现有 bootstrap 兜底能力。

### 稳定后：两个都应退出默认主线

当新的统一入口满足下面条件后，这两个带有 `Temporary` 的 workflow 都应从默认主线删除，或移到明确的 recovery / archive 区：

1. runtime 版本已经统一；
2. base + small 模型解析已经统一；
3. CLI Artifact 和模型 Artifact 可以被 bridge 自动消费；
4. VAD 已进入统一执行链；
5. `smoke_test.sh` 可以在干净环境通过；
6. 一条真实音频可以从原始媒体跑到 transcript + manifest；
7. 手机和电脑使用同一个高层入口；
8. 不再依赖 1 天 Artifact 作为长期运行时。

### 不建议长期保留当前 1.7.6 build workflow 作为“正式发布”

理由：

- 当前 runtime lock 指向 1.9.2；
- 构建参数固定为 AVX/AVX2/FMA，属于特定 Linux x64 CPU 假设；
- 只上传裸 `whisper-cli`；
- 1 天后 Artifact 自动失效；
- 目前没有版本化发布和校验桥接。

它更适合作为临时恢复工具，而不是正式 distribution。

---

## 目标：最终只保留一个高层入口

最终不应该让使用者手动依次运行两个 workflow、下载 Artifact、改名、解压、移动模型再运行 Python。

目标接口应该是：

```text
输入：原始媒体
↓
自动检查运行时
↓
自动准备 VAD / CLI / 模型
↓
自动桥接到固定 runtime 目录
↓
smoke test
↓
完整转写
↓
必要时 small 精转
↓
输出 transcript + srt + json + manifest
```

建议后续收敛成：

```text
一个脚本入口
或
一个统一 workflow_dispatch
```

而不是继续增加第三、第四个彼此独立的临时 workflow。

---

## 电脑端使用

### Linux x64

这是当前 whisper.cpp 便携构建最接近的目标环境。

前置条件：

```text
git
python3
ffmpeg
```

克隆仓库后，先准备 runtime 资产，再运行：

```bash
bash 语音转文字/tests/smoke_test.sh

python3 语音转文字/scripts/transcribe_media.py \
  "/path/to/recording.m4a" \
  --output-dir "./output" \
  --strength base \
  --language zh
```

### macOS / Windows

当前 GitHub Actions 生成的是 Linux x64 `whisper-cli`，不能直接当作 macOS / Windows 通用二进制。

可选路径：

- 在对应系统原生构建 whisper.cpp；
- Windows 使用 WSL 运行 Linux 路径；
- 使用云端 Linux runtime；
- 走 `faster-whisper` 路径；
- 后续增加按平台发布的版本化二进制。

不要把当前 `whisper-cpp-176-portable-linux` 理解为“所有电脑都能直接运行”。

### 当前 faster-whisper + VAD 路径

在支持 bash + Python 的环境中：

```bash
RUNTIME_PYTHON="$(scripts/ensure_runtime.sh)"

"$RUNTIME_PYTHON" scripts/transcribe_audio.py \
  "/path/to/recording.m4a" \
  --output-prefix "./output/recording" \
  --language zh
```

这条路径当前已有 VAD，但输出结构与 `语音转文字/scripts/transcribe_media.py` 不完全相同，因此现阶段把它视为 **VAD/备用 ASR 路径**，而不是已经完成统一的主入口。

---

## 手机端使用

手机端的原则是：

**手机只负责提供原始媒体和发起任务，不要求手机本地编译或运行 Linux x64 whisper-cli。**

### 当前可行方式

1. 在手机上保留原始录音 / 视频；
2. 把原始媒体上传到实际执行环境；
3. 由云端、电脑或支持该 Skill 的运行环境执行 runtime 解析和 ASR；
4. 最终把 transcript / SRT / JSON / manifest 返回给手机继续查看或分析。

如果通过 GitHub 手机网页 / App 操作：

- 可以手动触发两个 bootstrap，或运行 `ASR end-to-end smoke` 验证固定短语音链路；
- 可以查看构建状态；
- 可以在 Artifact 过期前下载产物；
- 但 **当前两个 workflow 都不能接收你的录音并直接完成转写**。

因此手机端现在不应该被描述为“打开 GitHub Actions 就能完成语音转文字”。

### 手机端最终目标

移动端最终只需要一个动作：

```text
上传原始媒体 → 发起转写
```

运行时准备、VAD、模型、CLI、桥接和实际转写都应该由执行端自行完成。

---

## GitHub Actions 当前的正确定位

### `asr-smoke.yml`：端到端短语音 CI

运行入口：GitHub Actions → **ASR end-to-end smoke** → **Run workflow**。相关脚本、tests、runtime lock、此 workflow 或根 README 的 push / pull request 也会触发。使用 Ubuntu 24.04、只读仓库权限，单个 job 最长 25 分钟，实际转写步骤最长 5 分钟。

执行顺序：

1. 读取 `runtime/runtime-lock.json` 的版本、默认模型名与 `base_q5_1` URL；当前为 **whisper.cpp 1.9.2 + ggml-base-q5_1.bin**，不会降级到旧 bootstrap 的 1.7.6 或 small。
2. 从 whisper.cpp 官方对应 tag 构建 CPU CLI，关闭 shared libs，并安装到 `语音转文字/runtime/whisper-bin-ubuntu-x64/whisper-cli`；base 模型下载到现有 runtime 根目录。记录上游 commit 和模型 SHA-256。首次 CI 已验证该 lock 的 base URL 返回 404；CI 保留它为首选，下载失败时明确告警并使用 whisper.cpp 官方 Hugging Face 同名模型，固定到修订 `5359861c739e955e79d9a303bcbc70fb988958b1`。两条下载路径均核对官方 LFS SHA-256 `422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898`，实际来源记录在 `model-source.txt`；双源失败或哈希不符会直接失败，不更换模型或 CLI 版本。此补充仅用于 CI，未修改 runtime lock。
3. 复用现有 bootstrap / `smoke_test.sh` 预检；用 espeak-ng 本地生成约十秒英文语音，再转成 44.1 kHz 双声道 FLAC，交给现有 `transcribe_media.py` 解码、标准化和推理。测试显式传入固定 CLI/model 路径，使用 base、英文、2 线程及 `--force`，避免其他缓存或旧 manifest 掩盖故障。
4. 检查所有产物非空、JSON 可解析且有转写段落、SRT 时间轴递增且位于音频范围内、TXT/SRT/JSON 文本一致、带时间戳逐字稿与 SRT 一致、至少识别三个测试关键词、标准化 WAV 为 16 kHz 单声道 PCM16，以及 manifest 源 SHA-256、文件大小、引擎、语言、模型和产物路径。

英文合成语音只验证工程链路，不代表中文准确率、长录音尾段覆盖、VAD、说话人识别或 small 精转已经验收。本次保持原有生产脚本、runtime lock 和两个临时 workflow 不变。

**产物与失败排查**：每次运行使用新的输出子目录。`always()` 上传 `asr-smoke-<run_id>-<run_attempt>`，保留 **14 天**（受仓库保留政策约束）；其中包括生成的测试媒体、预期文本、TXT/SRT/JSON/manifest、`validation.json`、构建/下载/预检/转写日志、runtime lock 副本、上游 commit、实际模型来源、模型哈希及校验日志和环境诊断。模型与 CLI 二进制不上传、不缓存，每次从干净 runner 准备，避免依赖 1 天 Artifact。早期失败时只有已生成的日志；runner 丢失或强制终止时上传无法保证。先看首个失败步骤，再查看同名日志；修复依赖/网络或代码后重跑任务即可。

在已准备相同 runtime 且安装 Python 3、FFmpeg、espeak-ng 的 Linux 环境，可直接复现转写与产物检查：

```bash
bash 语音转文字/tests/e2e_smoke_test.sh /tmp/asr-smoke-results
```

新增 workflow 的完成标准是：干净 runner 完成上述四步、`validation.json` 为 `passed`，且产物可下载。仓库提交、静态校验与实际 CI 通过是三个不同状态；首次运行状态请查看 Actions。完整业务链路仍需满足文末其余完成标准。

### `fetch-whisper-small-q5.yml`

当前用途：

- 解决当前环境不能直接从模型源下载时的临时桥接；
- 产出 `ggml-small-q5_1.bin`；
- Artifact 保留 1 天。

它 **不是完整模型管理 workflow**，因为：

- 目前没有 base；
- 没有 tiny fallback；
- 没有把产物桥接到 runtime；
- 没有调用转写；
- 没有 transcript 输出。

### `build-whisper-portable.yml`

当前用途：

- 临时构建 whisper.cpp 1.7.6；
- 关闭 shared libs；
- 关闭 native / AVX512 / AVX-VNNI / AMX；
- 开启 AVX / AVX2 / FMA；
- 只构建并上传 `whisper-cli`；
- Artifact 保留 1 天。

它 **不是完整便携 runtime 发布流程**，因为：

- 没有与 runtime lock 对齐；
- 没有打包 bootstrap 期待的目录/压缩结构；
- 没有模型；
- 没有 VAD；
- 没有真实媒体 smoke transcription；
- 没有跨平台产物。

---

## 下一步稳定化顺序

后续改代码时，建议严格按下面顺序做，不再新增孤立组件：

1. **统一 whisper.cpp 版本**：1.7.6 与 1.9.2 只保留一个标准；
2. **补 bridge 层**：让裸 CLI / 裸 BIN / zip / session cache 都能归一化到固定 runtime 路径；
3. **补 base 模型解析**：不能只依赖 small；
4. **把 VAD 收进统一入口**：决定使用 faster-whisper VAD、独立 VAD，或其他固定实现；
5. **持续验证端到端 smoke CI**：新增 `asr-smoke.yml` 已实现这条检查；每次以对应提交的绿色运行及产物为通过证据；
6. **增加单一高层入口**：脚本或统一 GitHub workflow；
7. **跑一条真实长录音**：确认 transcript、SRT、JSON、manifest 和关键片段精转都能复用；
8. **再删除两个 Temporary workflow**。

这套顺序的核心原则是：

> 先把“资产能找到、路径能对上、干净环境能跑通”解决，再优化模型质量和分析层。否则每次语音转文字都会重新经历运行时寻找、模型寻找、桥接失败和重复下载。

---

## 完成标准

语音转文字链路只有同时满足下面条件，才算真正稳定：

- 原始媒体就是足够输入；
- 手机和电脑不需要两套不同 SOP；
- FFmpeg 标准化可自动完成；
- VAD 有明确且唯一的执行位置；
- CLI 版本有唯一 lock；
- base / small 模型来源和缓存路径明确；
- GitHub Artifact 可以自动 bridge，而不是人工改名搬文件；
- 干净环境中的 `ASR end-to-end smoke` 全部步骤成功，且 `validation.json` 为 `passed`；仅文件检查通过、workflow 已提交或 Artifact 上传成功均不算端到端通过；
- 实际录音可以直接产出带时间戳逐字稿；
- manifest 可以按源文件 hash 复用；
- 关键节点可以 small 二次精转；
- 下游 Call 分析引用真实时间戳和原话；
- 1 天 Artifact 失效不会让整套流程瘫痪。

在这之前，现有两个 Temporary workflow 应被视为 **bootstrap 工具**，而不是最终工作流。
