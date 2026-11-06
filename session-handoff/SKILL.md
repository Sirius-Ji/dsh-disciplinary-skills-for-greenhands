---
name: session-handoff
description: Use at the start of every task and when closing it; if the workspace has no HANDOFF.md, create the skeleton immediately and run the archive protocol — a three-file handoff protocol (HANDOFF.md / ARCHIVE.md / ARCHIVE_INDEX.md) that keeps the latest progress in context while the full history stays off-context, retrieved by index plus anchored grep instead of wholesale reads. 会话交接、进度接力、归档索引、grep 检索、上下文溢出、跨会话接手.
---

# SKILL：会话交接（Handoff）

**触发（强制，无前置条件）**：**每次任务启动或收尾时使用；若工作区没有 `HANDOFF.md`，必须立即创建骨架并执行归档流程。**

**不适用**：无。它是强制项——不存在「工作区还没有交接文件，所以这轮不用做」这种豁免。

## 一、三个文件

| 文件 | 体量 | 读写规则 |
|---|---|---|
| `HANDOFF.md` | ≤120 行 | **覆写**，只保留最新进度 |
| `ARCHIVE.md` | 无上限 | **只追加**，永不重写、永不删除 |
| `ARCHIVE_INDEX.md` | 每行一条 | **只追加行**，不改已有行 |

## 二、开工第一动作

读 `HANDOFF.md`（≤120 行，成本可接受）。**不要**读 `ARCHIVE.md`，哪怕"只是看看有多大"。

## 三、写入：严格三步顺序

1. **追加 ARCHIVE** — 把当前 `HANDOFF.md` 全文**原样**追加到 `ARCHIVE.md` 末尾，前置锚点行：

   ```
   ## [2026-11-02T14:30+08:00] H-0042 <slug>
   ```

2. **覆写 HANDOFF** — `updated_at` 换成当前时间，`archive_anchor` 填上一步的 ID。
3. **追加 INDEX 一行** — 追加到**表格最后一行下方**（`| H-00xx |` 那行之后），**不是文件末尾**；
   INDEX 表格后面还有「分卷状态」章节，机械 append 到文件尾会把行插进章节里，索引表格当场断掉
   （2026-11-06 `H-0023` 实测踩中：一行掉在「## 分卷状态」下面，靠人工搬回才修好）。

   ```
   | H-0042 | 2026-11-02T14:30 | 1241-1302 | 交接机制设计 | handoff,archive,grep |
   ```

顺序不可颠倒：中途崩溃时最坏是 INDEX 少一行（可重扫锚点重建），`ARCHIVE.md` 永不被破坏。

**必须用命令搬运，不得由模型重述内容。**Python bytes 版（最稳，不经过行尾翻译）：

```python
hb = open("HANDOFF.md", "rb").read()
with open("ARCHIVE.md", "ab") as f:
    f.write(anchor_line.encode("utf-8") + b"\r\n" + hb)
```

PowerShell 版（注意 `-NoNewline`，否则会多出空行）：

```powershell
Get-Content HANDOFF.md -Raw | Add-Content ARCHIVE.md -NoNewline -Encoding utf8
```

## 四、检索：禁止整读 ARCHIVE

1. 读 `ARCHIVE_INDEX.md` 定位锚点 ID；
2. 按锚点精确 grep：

   ```powershell
   Select-String -Path ARCHIVE.md -Pattern 'H-0042' -Context 0,40
   ```

3. 需范围读取时按已知行号 `read offset/limit`，**单次不超过 80 行**。

**行号只是提示**：只有严格 append-only 时行号才稳定。检索以**锚点 ID** 为准，行号仅作加速。

## 五、更新频率

- 每个子任务完成 ⇒ 必须更新；
- 单个子任务超过 8 轮 ⇒ 强制插一次。**用 todo 阶段边界做机械锚点，不要靠模型数轮次**（不可靠）；
- 用户说"更新交接" ⇒ 立即执行。

## 六、禁止项

- ❌ 一上来 `read ARCHIVE.md`；
- ❌ 用"总结"替代原文归档 —— **无损追加是硬要求**；
- ❌ 删除或重写 ARCHIVE 历史；
- ❌ 修改 INDEX 已有行（行号漂移以锚点 ID 为准）；
- ❌ 把 HANDOFF 写成第二个 ARCHIVE（必须 ≤120 行）。

## 七、HANDOFF.md 模板

```markdown
# HANDOFF — <项目名>

updated_at: 2026-11-02T14:30:00+08:00
archive_anchor: H-0042
next_action: 一句话说清"接手后第一个该做的动作"

## 目标
（这一轮要交付什么，1-3 行）

## 已完成
- [x] …（每条带证据：文件/命令/校验结果）

## 未完成 / 下一步
- [ ] …（按优先级；第一条就是接手后的第一个动作）

## 卡点与决策
- 卡在哪、试过什么、为什么放弃（含当时数字）

## 关键路径
- 涉及的文件、脚本、配置（绝对路径）
```

## 八、ARCHIVE_INDEX.md 格式

```markdown
| 锚点 | 时间 | ARCHIVE 行号 | 任务 | 检索关键词 |
|---|---|---|---|---|
| H-0041 | 2026-11-02T13:20 | 1180-1240 | DSH 升级收尾 | 0.2.1-rc.5,pnpm,store,431 |
```


## 九、分卷规则（什么时候切开 ARCHIVE）

**阈值（任一满足即分卷）**

| 指标 | 阈值 | 为什么是它 |
|---|---|---|
| INDEX 行数 | > 800 行 | INDEX 是**要被读**的导航文件；按 133 B/行算，800 行≈106 KB≈3 万 token，再大就会诱导整读 |
| 单个 ARCHIVE 体积 | > 5 MB | grep 对 5 MB 是秒级（不是瓶颈），但这条能彻底掐掉"整读冲动" |
| 锚点数 | > 1500 | 与前两条互为兜底 |

**实测参考**（2026-11-02，某项目）：ARCHIVE 81 KB / 1,760 行 / 91 个锚点，INDEX 13 KB / 91 行。
⇒ 距 INDEX 阈值还有 8.8 倍、距 ARCHIVE 阈值还有 63 倍。**当前明确不需要分卷**，但规则先定好。

**分卷做法（必须无损）**

1. 按**自然阶段**切（发布节点 / 月份 / 大任务收尾），**不按体积硬切**；
2. 旧卷改名冻结：`ARCHIVE-<YYYY>Q<n>.md` 或 `ARCHIVE-<序号>-<H-起>~<H-止>.md`，设为只读；
3. 新卷继续只追加；
4. `ARCHIVE_INDEX.md` 增加一列「卷」，每行指向所在卷；
5. **禁止**：删改已冻结卷、用摘要替代原文、把单条锚点跨卷挪动。

**检索顺序**：INDEX 定位「卷 + 锚点」→ 只在那一卷里 grep，不要跨卷全文扫。

## 十、压缩存活复验（`/compact` 之后必做）

**为什么有这一节**：压缩会把上下文压成摘要，纪律文件还在不在、门禁还跑不跑得起来，**只能测，不能猜**。
2026-11-06 实测：压缩后 `AGENTS.md` 逐字节没变，但如果不先锁基线数字，就分不清"真的没变"和"我以为它没变"。

### 第一步：压缩前就把基线锁成具体数字

只写"等下验证一下"等于没有断言——压缩后说什么都算对。至少要锁这四项：

| 锁什么 | 怎么取 | 示例（2026-11-06） |
|---|---|---|
| 字节数 + 字符数 | `len(b)` / `len(t)` | 6019 B / 3123 字符 |
| sha1 / sha256 前缀 | `hashlib.sha1(b).hexdigest()[:12]` | `a5abfc79322c` / `F624CB8B` |
| 条目数 | 正则数 `^- ` 与 `^## ` | 22 条 / 7 节 |
| 门禁退出码 | 真跑一次并记下 | `check_handoff.py` → `exit 0` |

### 第二步：压缩后分两类口径，不许混

| 内容类型 | 生活在哪里 | 正确验法 | 错误口径 |
|---|---|---|---|
| 纪律（`AGENTS.md`） | 被宿主**注入上下文** | 压缩后有没有**重新注入**、digest 是否等于磁盘 sha1 | "我记得有这条" |
| 技能（`SKILL.md`） | **只在磁盘**，按需加载 | 当场 `skill("<名字>")` 能不能加载出全文 | "基线里没看到 ⇒ 丢了" |

原理性内容永远不在上下文基线里。拿"基线里有没有"去验技能，结论必然是假的。

### 第三步：判据只认退出码 + digest

```powershell
node skills/tools/verify_discipline_channel.mjs --require-compaction --cross-session
```

看输出里那句"✓ PASS"不算数——那是脚本自己说的。要同时满足三条：

1. 退出码 0；
2. 最后一次 `compaction/end` 之后**确实有**根通道注入记录（`action=set|replace`、`baseline=true`）；
3. 那条注入的 `digest` == 压缩前锁的 sha1。

### 第四步：顺手验一次"按需加载"

压缩后立刻调一次 `skill()` 加载任一技能。这不是走过场，它同时证明了两件事：
技能文件还在、技能加载通道没被压缩搞坏。技能正文本身不需要待在上下文里。

### 踩过的坑

- 压缩前不锁数字 ⇒ 压缩后无法证伪，结论只能是"我觉得在"。
- 把技能当成"基线内容"去验 ⇒ 必然误判丢失（技能从来就不进基线）。
- **行尾规矩别外推**：`AGENTS.md` 与所有 `SKILL.md` 是**纯 CRLF**，
  而 `HANDOFF.md` / `ARCHIVE.md` / `ARCHIVE_INDEX.md` 是**纯 LF**。
  2026-11-06 就因为按 CRLF 处理 `ARCHIVE.md`，被自己的断言当场拦下（零字节落盘）。
