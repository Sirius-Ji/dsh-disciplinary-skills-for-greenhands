---
name: windows-path-damage-diagnosis
description: Diagnose a PATH or environment variable that suddenly broke on Windows — commands that used to work now fail with 「不是内部或外部命令」「无法将…项识别为 cmdlet」 or 「command not found」, or a tool (xelatex, git, node, python) vanished after installing something or after PATH got truncated. Proves the damage time from the registry key LastWriteTime, keeping forensics read-only before any repair. PATH 损坏、环境变量、命令找不到、xelatex 丢失.
---

# SKILL：PATH 损坏排查与恢复

**适用症状**

- 某命令**突然**"找不到"（本机案例：`xelatex` 丢失 → 答疑公式渲染全挂）
- 但打开"环境变量"看 PATH **似乎"没动过"**（长串里少几个字符肉眼看不出来）
- **"重启后好了一次、再开又坏"**——其实不是"好了一次"，而是：进程只在**启动时读一次**环境，
  已经跑着的旧进程一直用旧 PATH；新开的进程若在修复前启动，也还是旧 PATH
- 同一台机器上，"你在终端里能跑通"但"应用里说找不到"（两者继承的 PATH 不同）

**不适用**

- 命令**确实被卸载/删除**（先 `Test-Path` 确认可执行文件还在）
- 只是**当前会话**的临时改动（`$env:PATH=...`），关掉即恢复
- 应用自己配置里写了错误路径（那要改配置，不是改 PATH）

---

## 快速判断（30 秒）

```
1. 新开一个终端（不是旧的！）：
       where.exe <关键命令>          # 找不到 → 继续
2. 读 HKLM 的 Path 原文，找"分号插进路径中部"的畸形条目：
```

| 畸形形态 | 含义 |
|---|---|
| `C:;Program Files\...` | 分号紧跟在**冒号后**——盘符与路径被切断 |
| `D:\Pro;ram Files\...` | 分号插在**单词中部**——字符串被从中间截断 |
| `C:\Program Files\...` 正常 | 对照组：盘符 + 反斜杠 + 目录 |

```
3. 两条畸形条目 = 100% 人为写入截断，不是"系统本来就这样"
```

**判据一句话**：正常 PATH 条目长 `X:\...`；出现 `X:;` 或 `X:\Xxx;Yyy` （分号后不接盘符/`%`）
即可判定**被写入方截断**。

---

## 核心原则

### 原则 1：LastWriteTime 是"损坏时刻"的决定性证据

"PATH 变了没有"不要靠肉眼比对长串——**读注册表键的最后写入时间**。
键级时间戳不受值内容影响，只要有人写过就变。

### 原则 2：进程环境 ≠ 系统环境

进程启动时**拷一份**环境副本，之后系统怎么改都与它无关。
⇒ 任何"验证修复"的操作，必须用**新进程**或**从注册表重读**。

### 原则 3：只读取证，写操作留给人工

排查全程只读（读注册表 / 读日志 / 读历史 / 查进程）。
PATH 的**写**一律由人在"系统属性 → 环境变量"里手工完成——
改错了会让整台机器的命令行全线失效，风险与收益不对称。

### 原则 4：先备份，再修改

改注册表前导出 `.reg`。PATH 是"全局单点"，改坏的爆炸半径是整机。

---

## 根因定位（系统级证据，全只读）

按证据强度排序，**1 与 3 是主证据**：

### 1. HKLM Environment 键的 LastWriteTime（决定性）

`Path` 存在 `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment`。
`RegistryKey` **不直接暴露** LastWriteTime，两条路：

**PowerShell（P/Invoke `RegQueryInfoKey`）**

```powershell
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class RegTime {
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode)]
    static extern int RegQueryInfoKey(IntPtr hKey, System.Text.StringBuilder c, IntPtr a, IntPtr b,
        out int s, out int m1, out int m2, out int v, out int m3, out int m4, IntPtr d, out long ft);
    public static DateTime Get(long h) {
        int a,b,c,d,e,f; long ft;
        int rc = RegQueryInfoKey(new IntPtr(h), null, IntPtr.Zero, IntPtr.Zero,
                                 out a, out b, out c, out d, out e, out f, IntPtr.Zero, out ft);
        if (rc != 0) throw new Exception("rc=" + rc);
        return DateTime.FromFileTime(ft);
    }
}
'@
# 键句柄：从 .NET RegistryKey 的私有字段 hkey 反射（它是 SafeRegistryHandle）
function KeyTime($hive, $path) {
  $k = $hive.OpenSubKey($path)
  $f = $k.GetType().GetField('hkey', [System.Reflection.BindingFlags]'NonPublic,Instance')
  [RegTime]::Get($f.GetValue($k).DangerousGetHandle().ToInt64())
}
KeyTime ([Microsoft.Win32.Registry]::LocalMachine) `
        "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
```

> 坑：`hkey` 字段是 `SafeRegistryHandle`，**不能**直接 `[IntPtr]` 强转，
> 必须先 `.DangerousGetHandle()`。

**Python（`winreg`，更省事）**

```python
import winreg
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as k:
    value, _ = winreg.QueryValueEx(k, "Path")
# 注意：winreg 不返回键时间；键时间用上面 PowerShell 那段
```

### 2. 对比 HKCU\Environment 的 LastWriteTime

同一个 `KeyTime` 函数换 `CurrentUser` + `"Environment"`：

| 观察 | 结论 |
|---|---|
| HKLM 与 HKCU 时间**相同**（秒级） | 某工具一次写了**整个**环境（两级一起动） |
| 时间**不同**、相差几十分钟 | 是**两次独立**写入，要分别找各自的肇事者 |
| 只有 HKLM 变 | 专门改**系统变量**的工具（多数安装器） |
| 只有 HKCU 变 | 用户级脚本 / 应用自设（本机案例：DSH 修用户级 PATH） |

### 3. PSReadLine 命令历史（找"当时敲了什么"）

```
%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt
```

**技巧**：看**文件自身的 mtime**——它 ≈ 最后一次在该窗口敲命令的时刻，
与"注册表键写入时间"一比对，就能把肇事命令锁到分钟级。

```
Get-Item $env:APPDATA\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt |
  Select-Object Length, LastWriteTime
Get-Content <该文件> -Tail 20
```

### 4. 事件日志（损坏时刻 ±30 分钟）

```powershell
# 应用日志：安装器
Get-WinEvent -FilterHashtable @{LogName='Application';
    StartTime=[datetime]'2026-10-01 14:20:00'; EndTime=[datetime]'2026-10-01 15:20:00'} |
  Where-Object { $_.ProviderName -match 'MsiInstaller|Setup|Install' } |
  Select-Object TimeCreated, ProviderName, Id, Message

# 系统日志：服务变更 / 驱动 / 更新
Get-WinEvent -FilterHashtable @{LogName='System';
    StartTime=[datetime]'2026-10-01 14:20:00'; EndTime=[datetime]'2026-10-01 15:20:00'} |
  Where-Object { $_.ProviderName -match 'Service Control Manager|Setup|Kernel-PnP|WindowsUpdateClient' }
```

**辅助线索**

```powershell
# 按安装日期找最近装了什么
Get-ItemProperty 'HKLM:\SOFTWARE\*\Microsoft\Windows\CurrentVersion\Uninstall\*',
                 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' |
  Where-Object InstallDate -ge '20261001' | Select DisplayName, DisplayVersion, InstallDate

# 补丁/驱动安装痕迹
(Get-Item $env:SystemRoot\Logs\CBS\CBS.log).LastWriteTime
(Get-Item $env:SystemRoot\INF\setupapi.dev.log).LastWriteTime
```

### 5. PATH 损坏形态分析

| 形态 | 根因 |
|---|---|
| 分号插在路径中部（`D:\Pro;ram Files\`） | 写入方**读旧值 → 拼接新条目 → 写回**时按错误偏移截断 |
| 末尾多出一条正常新路径（`;C:\Program Files\Git\cmd`） | 就是**这次安装**新加的那条（它是完好的） |
| 多条**不同位置**被截断 | 排除"单点字符丢失"，坐实"整体重写"（长度/偏移类 bug） |
| 值里带 `%VAR%` 却写成了 `REG_SZ` | 变量不再展开（应保持 `REG_EXPAND_SZ`） |

**判据**：`reg query <键> /v Path` 直接看原文类型（`REG_EXPAND_SZ`）与全文。

---

## 修复（手动，不让 AI 碰）

```
1. 备份：
   regedit → HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment
   → 右键 Path → 导出 → 存 xxx-Path-backup-<日期>.reg

2. 打开 GUI：
   Win+R → sysdm.cpl → 高级 → 环境变量

3. 【系统变量】区里找 Path（⚠️ 不是"用户变量"）
   区分方法：系统变量里有 C:\Windows\system32

4. 删掉畸形条目 → 点"新建" → 用【浏览】按钮选目录（别手打路径）
   —— 加完整路径比在长串里改字符安全得多

5. 一路"确定"到底（每层都要点，否则不落库）

6. 【关键】验证真的落库了（见下节）
```

**为什么不让 AI 改**：PATH 是全局单点，写坏 = 整机命令行失效（连 `powershell`、`where.exe`
都可能找不到）。手工改有 GUI 校验，风险最低。

---

## 验证（关键陷阱）

### ❌ 陷阱 1：复用会继承旧环境的进程

**本机案例**：DSH 宿主进程 21:18 启动时 PATH 还是坏的 → 它派生的子进程**继承旧环境**
→ 第一次验证得 `is_available() = False`（**假阴性**，让人误以为修复失败）。

```
❌ 在旧终端里跑 python -c "from src.qa import math_render; print(math_render.is_available())"
✅ 新开终端跑，或从注册表重读环境后跑
```

**正确做法（不改 PATH，只重建本次进程环境）**

```powershell
$m = [System.Environment]::GetEnvironmentVariable('Path','Machine')
$u = [System.Environment]::GetEnvironmentVariable('Path','User')
$env:PATH = $m + ';' + $u          # 用系统现值重建，等价于"新开的终端"
where.exe xelatex
```

Python 侧同理（`winreg` 读注册表，避免 subprocess 的 GBK 解码坑）：

```python
import os, winreg
def read_path(scope, subkey):
    root = winreg.HKEY_LOCAL_MACHINE if scope == "Machine" else winreg.HKEY_CURRENT_USER
    with winreg.OpenKey(root, subkey) as k:
        return winreg.QueryValueEx(k, "Path")[0]
os.environ["PATH"] = read_path("Machine", r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") \
                   + ";" + read_path("User", "Environment")
```

> 坑：用 `subprocess` 调 PowerShell 读 PATH 会因**中文路径 + GBK 解码**炸掉
> （`UnicodeDecodeError: 'gbk' codec can't decode byte 0xaa`）。**直接用 `winreg`。**

### ❌ 陷阱 2：只信"新终端能跑"

"新终端能跑"**不能**证明注册表改对了——用户可能只改了当前会话的 `$env:PATH`（内存），
一关就没。**必须**两条硬证据同时成立：

| 证据 | 判据 |
|---|---|
| 注册表键时间戳 | HKLM Environment 的 LastWriteTime **变了**（不再是事故时刻那个） |
| 注册表值内容 | 畸形条目已消失、完整路径已出现 |
| 新进程可见性 | **新开的**终端里 `where.exe <命令>` 能找到 |

### ❌ 陷阱 3：把"应用里还是找不到"当成没修好

已经开着的应用不会重读环境。**必须重启应用**（不是重启机器）。

---

## 预防

- **装/更新任何会写 PATH 的软件后**（安装器、版本管理器、SDK、新语言运行时），
  立刻在新终端 `where.exe <你依赖的关键命令>` 验一遍。
  本机案例：`winget install Git.Git` 之后没人验，损坏潜伏 4.8 小时才以"公式渲染全挂"暴露。
- **改 PATH 用"浏览"按钮选目录**，别手打——**中文用户名/中文目录尤其危险**
  （编码边界 + 长值截断）。本机案例里两条被截断的条目**都含中文路径**。
- **定期导出 PATH 的 `.reg` 备份**（改之前必导，改之后也导一份"已知良好"版本）。
- **关键命令路径硬编码进项目配置**，别只依赖 PATH。
  本机案例的正解：`math_render` 加"候选路径探测"
  （`shutil.which` 失败后依次试 `%ProgramFiles%\MiKTeX\...`、`%LOCALAPPDATA%\Programs\MiKTeX\...`、
  `C:\texlive\<年>\bin\windows\` 等）—— 环境再坏也不影响功能。**这是"方案 B"，尚未做。**
- **别用 `setx` 改 `PATH` 这类长变量**：`setx` 有 1024 字符截断限制，
  正是"分号插进路径中部"这类损坏的常见成因。要改就用 GUI 或
  `[Environment]::SetEnvironmentVariable('Path', $v, 'Machine')`。

---

## 反模式

### ❌ 肉眼比对长串 PATH

200+ 字符里少几个字符看不出来。**要用"形态判据"**（分号位置）+ **LastWriteTime**。

### ❌ 用 `setx` 写 PATH

1024 字符上限 + 无校验，是损坏的高发来源。用 GUI 或 `SetEnvironmentVariable`。

### ❌ 在旧进程里验证

继承旧环境 ⇒ 假阴性（本机踩过）。要么新开终端，要么从注册表重读。

### ❌ 让 AI/脚本直接写 HKLM PATH

爆炸半径 = 整机命令行。**人工 GUI 改，AI 只做只读取证 + 验证。**

### ❌ 只改"用户变量"

`sysdm.cpl` 里"用户变量"和"系统变量"两个 Path 长得很像；
装到系统目录的工具通常只登记在**系统变量**里。改错区 = 白改。

### ❌ 改完不点完所有"确定"

每层对话框都要点"确定"，中途按"取消"或直接关窗 = 不落库。

---

## 边界

### 能定位

- 损坏的**确切时刻**（键 LastWriteTime，毫秒级）
- **可疑肇事者**（PSReadLine 历史 + 事件日志 + 安装日期，可到分钟级）
- 损坏**形态与成因类别**（截断 / 类型错 / 区域改错）

### 不能 100% 归因

- 注册表**不记录"谁写的"**：只能靠"同一时刻还有什么在动"来推断
- 若肇事者是**无日志的 GUI 安装器**且恰好没有别的旁证，只能给出"高度可疑"

### 需要人工裁决

- 是否恢复**已失效的旧条目**（指向的目录可能早就不存在了，本机案例的
  `C:\Program Files (x86)\Tencent\微信web开发者工具` 就**不存在** —— 恢复一条死路径无意义）
- PATH 里该不该保留某条（业务判断）

---

## 一句话

> **键时间戳定时刻，命令历史定肇事；进程只信注册表现值，写操作交人工。**

---

# 附录：2026-10-01 完整案例

## 症状

答疑窗口重开，15 条历史记录（之前渲染过）全部显示 LaTeX 源码；
新对话回复也不渲染；归档草稿窗口点「预览公式」同样不渲染。
**三处同时失效 ⇒ 共用渲染层挂了。**

## 时间线（全部有系统级证据）

| 时刻 | 事件 | 证据 |
|---|---|---|
| 09-30 16:55 | 公式渲染正常（缓存 1048 个 PNG） | `data/tmp/math_cache/` |
| 10-01 13:33:36 | **最后一次**预热成功（2.1s） | `agent.log` |
| 10-01 14:16:58 | HKCU Environment 被写 | 键 LastWriteTime |
| 10-01 14:29:55 | DesktopAppInstaller 状态修复告警 | Application 日志 |
| **10-01 14:42:57.932** | **HKLM Environment 被写（损坏时刻）** | **键 LastWriteTime** |
| 10-01 14:43:15 | PSReadLine 历史落盘 | 历史文件 mtime |
| 10-01 19:30:30 | 桌宠重启读坏 PATH ⇒ **首次** `找不到 xelatex` | `agent.log` |

**肇事命令**（PSReadLine 历史最后两条）：

```
winget install Git.Git
git --version
```

**旁证**：`Uninstall` 键里 `Git 2.55.0.5 / InstallDate: 20261001`；
系统 PATH 末尾多出完好的 `;C:\Program Files\Git\cmd`（正是这次新增那条）。

**损坏形态**（`reg query` 原文，`REG_EXPAND_SZ`）：

```
...;C:\Users\<你的用户名>\AppData\Roaming\npm;C:;Program Files (x86)\Tencent\微信web开发者工具;
D:\Pro;ram Files\MiKTeX\miktex\bin\x64\;C:\Program Files\Git\cmd
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 两条被截断，位置各不相同
```

- `C:` + `Program Files (x86)\Tencent\微信web开发者工具`（盘符后截断）
- `D:\Pro` + `ram Files\MiKTeX\miktex\bin\x64\`（词中截断）

⇒ 两条**不同位置**截断 + 末尾新条目完好 = **安装器"读旧 → 拼接 → 写回"时按错误偏移截断**。

## 影响面

`xelatex` 唯一来源就是那条坏掉的 PATH 条目 ⇒ **公式渲染全挂**：

| 路径 | 检查点 |
|---|---|
| 答疑气泡（新消息 + 历史回填） | `BubbleMathController._enabled = enabled and is_available()` |
| 归档草稿「预览公式」 | `math_html.render_html()` 开头 `is_available()` |
| 归档/笔记出 PDF 的公式图 | `某个渲染模块` `math_render.is_available()` |

**共同单点：`is_available()`** —— 它用 `shutil.which("xelatex")` 探测，一 False 全废。

## 定位过程（可复用的顺序）

```
1. 配置无误（features.qa.math_render=True、dpi=400）
2. is_available() = False；shutil.which('xelatex') = None
3. 但 xelatex 二进制完好：D:\Program Files\MiKTeX\miktex\bin\x64\xelatex.exe
   （绕过 PATH 直接调用 --version 正常 ⇒ 引擎没问题，只是"找不到路"）
4. 读 HKLM Environment LastWriteTime → 14:42:57.932
5. 读 HKCU → 14:16:58.848（早 26 分钟，两次独立写入）
6. 读 PSReadLine 历史（mtime 14:43:15，紧邻损坏时刻）→ winget install Git.Git
7. 事件日志 ±30 分钟：无 MSI/驱动安装；14:42:14/14:42:44 有 IsolationSession
   服务启停（旁证"当时有东西在动"，非肇事者）
```

## 修复与验证

- **修复**：人工在 `sysdm.cpl` → 系统变量里修好两条（用户手动完成）
- **落库验证**：HKLM Environment LastWriteTime `14:42:57.932` → **`21:42:33.841`** ✓
- **可见性验证**：新进程 `where.exe xelatex` → `D:\Program Files\MiKTeX\miktex\bin\x64\xelatex.exe` ✓
- **踩过的坑**：第一次验证仍 `False` —— 因为 **DSH 宿主 21:18 启动时 PATH 还是坏的**，
  子进程继承旧环境 ⇒ 假阴性。改用"从注册表重读 → 重建进程环境"后立刻通过。
- **一个有价值的副产物**：`C:\Program Files (x86)\Tencent\微信web开发者工具`
  **目录本身不存在** ⇒ 恢复它只是恢复一条死路径（记录为"待清理"，未强行恢复）。

## 附带发现（另一个真 bug，已修）

`math_render.preheat()` 把公式连 `$` 定界符一起传给 `render_formula`：

```python
render_formula(r"$x^2$")                 # ✗ 被包成 $$x^2$$ ⇒ Missing $ inserted
render_formula(r"x^2")                   # ✓ 契约：不含定界符的内层公式
```

⇒ 每次开窗预热的两条公式**从来没成功过**（白烧 ~2s + 日志刷警告）。
全日志 8 条 `Missing $ inserted` 均源于此。**修复提交 `f7487d7`。**

## 缓存重建

PATH 修好后，磁盘缓存为空（`math_cache/` 0 个文件）⇒ 首次打开会逐条重编译（~1s/公式）：

```
预热真库 qa_history：245 个公式段 → 去重 239 个唯一公式
结果：成功 239 / 失败 0，耗时 237s（0.99s/个）
缓存：PNG 2 → 241（后续验收又补齐到 401 PNG + 401 JSON = 2.43 MB）
```

**验收（不带任何注入）**：模拟答疑窗口回填 20 条消息 / 170 个公式段
⇒ `render_html` **18.2 ms**（0.107 ms/公式，零降级）。

> 验收时又踩一个坑：第一次测出 **157 s**（全量重编译）。
> 原因是**竞态**——预热作业的最后一批文件写到 `21:52:29` 才结束，
> 而验收跑在 `21:51–21:52`，磁盘上只有约 81/241 个公式。
> **教训：长任务的"输出结束"不等于"写盘结束"；验收要等文件落盘（或按文件 mtime 确认）。**

## 本案例的三条可复用结论

1. **"看 PATH 似乎没动过"是错觉** —— 键 LastWriteTime + 形态判据（分号位置）两条一起上。
2. **"我们自己的进程"是最容易被忽略的验证障碍** —— 宿主进程比修复动作老，就一定在骗你。
3. **别让关键功能单点依赖 PATH** —— 加"候选路径探测"即可免疫（方案 B，未做）。
