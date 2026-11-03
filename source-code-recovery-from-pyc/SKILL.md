---
name: source-code-recovery-from-pyc
description: Recover a broken source file from its compiled artifact (.pyc, __pycache__, build output) when the original was destroyed by a bad write, encoding round-trip, or disk damage and git has no good copy to restore. Load this when a .py/.js source is unreadable, truncated, or full of mojibake while its compiled counterpart still exists. 源码损坏、文件变乱码、编码往返、pyc 反演、逐段修复、字节级恢复、回滚不了.
---

# Skill：源码事故恢复（基于 .pyc 反演）

**适用场景**：源代码文件被编码往返 / 磁盘损坏 / 误操作破坏，但存在可用的 `.pyc` 或等价编译产物。

**不适用**：

- 无 `.pyc` / 无等价参照
- 源代码被语义性篡改（不是字符级损坏）
- 需要恢复**注释内容**（编译器抛弃，无参照）

---

## 核心原则

### 原则 1：现场保全优先

事故发生后第一动作：**冻结快照，绝不在原文件上折腾**。

```
cp <损坏文件> <隔离目录>/<名字>.corrupted
```

### 原则 2：证据先于修复

**不猜，不试**。先建立完整证据体系：

- `.pyc`（编译产物，最权威）
- 编辑器 Local History / 同步盘 / 回收站（副本，若能找到则 100% 还原）
- 其他构建产物（`__pycache__`、打包产物）

### 原则 3：分层判据，硬证据优先

| 层 | 依据 | 守卫 |
|---|---|---|
| 1. 硬证据 | 本行 `.pyc` 拆段 / 本函数常量池 | 序列里没有的字符**不补** |
| 2. 同形推断 | 同族函数的同形句（真实 `.pyc` 常量） | 相似度阈值 + 记录来源 |
| 3. 语法唯一 | 语法强制（收尾引号等） | 只在“右侧无实义字符”时用 |
| 4. pure infer | 无来源 | **禁止** |

### 原则 4：编译验证 > 逐行推断

**逐函数独立编译 + `co_consts` 递归比对**是主判据。`ast.parse` 通过 ≠ 内容正确——静默丢字只有常量比对能抓。

### 原则 5：工具失败即手工

算法改 N 轮不收敛 → **立刻切手工落地**，别赌它会自己好。

---

## 流程

### 阶段 0：保全

```
1. 冻结损坏文件快照
2. 搜索副本（编辑器历史 / 同步盘 / 回收站 / 其他机器）
3. 有副本 → 直接用；无 → 进阶段 1
```

### 阶段 1：建立证据体系

```
1. 定位 .pyc（通常是 __pycache__/<name>.cpython-<ver>.pyc）
2. 校验 .pyc 与损坏源码的**编译版本**一致（Python 版本要匹配）
3. 反演：marshal.loads(pyc.read_bytes()[16:])
4. 建“函数级常量池”表
```

### 阶段 2：损伤分析

```
1. 识别损伤类型：
   - 字符被吞（编码往返）
   - 字符被替换（乱码）
   - 结构丢失（行/块）
2. 分类损伤点：
   - 代码态（阻塞编译）
   - 字符串内（影响内容）
   - 注释内（零影响，留白）
3. 优先修代码态
```

### 阶段 3：逐项修复

**对每个损伤点**：

```
1. 硬证据查询：
   - 本行 BUILD_STRING 拆段序列
   - 本函数 LOAD_CONST
2. 有 → 用硬证据填
3. 无 → 同形推断（同族函数）
4. 无 → 语法唯一（收尾定界符）
5. 无 → pending（人工裁决 / 运行时暴露）
```

**注意**：

- f-string 的拆段序列是**有序**的
- 单字符常量（`（`、`）`、`,` 等）要判断“是否为本行拆段序列的合法成员”
- `□` 是**不定长**占位符（1~4 字符）

### 阶段 4：验证

**三道门**：

```
1. ast.parse OK
2. co_consts 递归比对（逐函数）
3. --selftest / --smoke（如有）
```

**试跑验证**（不碰原文件）：

```
1. 复制整个项目到临时目录
2. 用恢复版替换目标文件
3. 跑起来看
```

### 阶段 5：写回

```
1. 备份当前版本
2. 写回
3. 校验：字节数 / 行数 / CRLF / bareLF
4. 立即验证：编译 + 测试
```

---

## 判据体系（可执行）

### 判据 1：函数级常量比对

```python
def verify_function(name, mine_src, pyc_src):
    mine = compile(mine_src, "<mine>", "exec")
    ref = marshal.loads(pyc_bytes[16:])
    return mine.co_consts == ref.co_consts  # 递归
```

**必须**：递归进嵌套 code object，否则漏掉 lambda / 内嵌函数里的差异。

### 判据 2：指令序列比对

`co_consts` 是**去重**的——同一字面量用两处 vs 用一处，常量池完全相同。**必须**用指令序列补上：

```python
dis.get_instructions(mine) == dis.get_instructions(ref)
```

### 判据 3：行号偏移检测

用“内容定位”而不是“行号映射”——行号会因吞换行而偏移。**锚点骨架**（标识符链匹配）+ **区间约束**（纯文案行落在哪两个锚点之间）。

### 判据 4：静默丢字扫描

逐行“源码文本 vs `.pyc` 模板”对齐，差异不含 `□` 但内容不同 → 静默丢字 / 换位型损伤。

---

## 工具清单（可参考实现）

| 工具 | 作用 |
|---|---|
| `fndump` | 按函数 dump 常量池 + BUILD_STRING 拆段 |
| `linedump` | 逐行字节码模板重建 |
| `namealign` | 标识符链主键 + 单调 DP |
| `extras` | 双向差集（consts / varnames / names / co_code） |
| `cdiff` | `co_consts` 递归比对 |
| `codesweep` | 指令序列比对 |
| `linescan` | 静默丢字 / 换位型扫描 |
| `stmtspan` | 语句跨度（`co_lines` run 区间） |

**补丁器必备**：

- read-back 断言
- 缩进守卫
- 引号前置校验
- 多行字符串索引（避免误杀 docstring 正文）

---

## 反模式

### ❌ 用 shell 改源码

```
(Get-Content file -Raw) -replace ... | Set-Content file   # 必坏
```

**正确**：用编辑器 / `read_text(encoding="utf-8")` + `write_text(encoding="utf-8")`。

### ❌ 用 PowerShell 处理含反斜杠 / 中文的字符串

同一个病根**踩过三次**（09-27 / 10-01 / 10-02），每次都表现为"看起来正常的静默损坏"。
按危险程度分三档：

| 档 | 写法 | 症状 | 实例 |
| --- | --- | --- | --- |
| ① 编码 | `Get-Content` / `Set-Content` **不带 `-Encoding`** | 中文损坏：中文 Windows 上默认按 GBK 解码，UTF-8 无 BOM 的文件被拆坏 | **09-27** `Set-Content` 往返把源码里的中文写坏 |
| ② 计数 | `(Get-Content $f).Count` 读行数 | **少算**：被拆坏的多字节字符让行数偏少 | **10-01** 744 行读成 632 |
| ③ 传参 | `-c` / `-Command` 里传含反斜杠的字符串 | **反斜杠被吃**：`"…\neq…"` 到 Python 手里变成 `…neq…`，且**不报错** | **10-02** 复核 A 组样本时先用 `-c` 传字符串，得出"样本被吃"的**错结论**；最后用 `ast.literal_eval` 对源码做字节级核对才定论 |

②档的现成实例（本文件自己，2026-10-02 实测）：

```
(Get-Content docs\recovery\source-code-recovery-from-pyc).Count          # → 195   ✗
[System.IO.File]::ReadAllLines($f, <UTF8 no-BOM>).Count          # → 264   ✓
```

差 69 行 —— 文件是 UTF-8 **无 BOM**，GBK 解码把多字节字符拆坏后就少了行。**没有任何报错**。

**正确**：

- **改源码/文档**：用 `read` / `edit` / `write` 工具，不要经 shell 参数转手；
- **必须用 shell 时**：读用 `[System.IO.File]::ReadAllText($f, [Text.Encoding]::UTF8)`
  或 `[System.IO.File]::ReadAllLines($f, (New-Object System.Text.UTF8Encoding($false)))`
  （显式无 BOM 编码）；写用 `[System.IO.File]::WriteAllText($f, $s, <UTF8 no-BOM>)`；
- **数行数**：一律走 `[System.IO.File]::ReadAllLines`，不用 `Get-Content`；
- **传字符串给程序**：先把文本写进文件，再用 `-F` / `--file` 入口传**文件路径**
  （如 `git commit -F <消息文件>`），绝不用 `-c` / `-Command` 直接传含反斜杠的正文；
- **要下结论前**：用**字节级核对**（`ast.literal_eval`、`repr()`、十六进制）验证，
  别信"shell 传过去看起来一样"。

### ❌ 用 PowerShell 传含引号的参数

PowerShell 会吞掉传给原生命令的双引号（`git commit -m "…\"…\"…"` 实测）。
即使不改源码，任何“通过 PowerShell 传递含引号文本”的操作都不可靠。
（与上一条同源：**凡是经 shell 参数转手的文本都不可信**，引号与反斜杠都属此列。）

**正确**：把文本写进文件，再用 `-F` / `--file` 之类的入口传文件
（`git commit -F <消息文件>`；实测用 `-m` 传正文时正文里的 `"` 会被吞掉）；
改文件本身则用编辑器或 `read` / `edit` / `write` 工具，不要经 shell 参数转手。

### ❌ 把 `.pyc` 当原文权威

`.pyc` 是**编译时快照**。如果源码在编译后被修改（修 bug），`.pyc` 会落后。

**识别信号**：

- 某处 `.pyc` 说“没有 X”，但源码有 X
- `co_names` 差异 + 语义上“源码这样写才对”

**处置**：保留源码版本，记“pyc 过期豁免”。

### ❌ 运行应用后信任 `__pycache__`

运行应用会重写 `.pyc`。**工具必须读受保护副本**。

### ❌ 子串批量替换

同一函数内相似片段必须**逐处用该处常量核对**。

### ❌ 分批修的推断值不复核

早期批次用推断（无硬证据）填充的位置，必须在编译通过后**统一复核**。

### ❌ 模板不匹配就当新形态

**先怀疑工具假阳性**（DATA_OPS 缺口、归属偏移、转义形态）。

---

## 边界

### 能恢复

- 代码逻辑（如果损坏是字符级）
- 字符串字面量、docstring、标识符
- 结构（如果 `.pyc` 有行表）

### 不能精确恢复

- **注释**（编译器抛弃，无参照）
- **`.pyc` 之后源码的修改**（如版本 B 的 bug 修复）

### 需要人工裁决

- 多个候选都说得通的损伤点
- 注释内容
- 涉及语义判断的“看起来该是这样”

---

## 前置条件

**最重要的前置**：项目有 `.pyc`（Python）或等价编译产物。

**最根本的预防**：**版本控制**。有 git 的项目，这类事故 10 分钟解决（`git checkout`），不需要 21 小时。

---

## 一句话

> 硬证据优先，编译验证为准，工具失败即手工，`.pyc` 是快照不是权威。
