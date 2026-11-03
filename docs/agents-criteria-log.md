# 判据留档（agents-criteria-log）

> 本文件由 `~/.dsh/skills/AGENTS.md` 于 2026-11-02 迁出（原为 HTML 注释块，占该文件 64.2%）。
> 内容是**历史取证与决策记录**，不是纪律；仅供参考，勿据此直接操作。
> 原始依据：三端 AGENTS.md 的 sha256 `43ec7157…`（8,297 B）。

---

判据留档（2026-10-31 更新，替代 2026-10-20 的 B1「不可行」结论）

     一、旧结论为什么过期
       旧记录：instructionSource 属于新版 minimal-prompt 插件行，而当时安装版 preset 无该行
       （19,219 B，仅 tool-bootstrap/custom-bash）⇒ 判定"硬加不生效"。
       实测（2026-10-31）：安装版 preset 已带该行 ——
         @linxin666/dsh-liangshen 0.4.4 · presets/liangshen/agent.cordis.yml 25,812 B / 10 文件
         L157 `- id: minimal-prompt` · L161 `instructionSource: host` · L162 `instructionMaxBytes: 65536`
         minimal-prompt.mjs 36,000 B 在盘上（`workspace-instructions` 段名见源码 L122）
       ⇒ 前提消失。`~/.dsh/.agent-presets/liangshen`（19,219 B / 5 文件）是 2026-09-28 的陈旧快照，
         没有任何配置引用它；plugins.json 记录的生效模块是 npm 包 @linxin666/dsh-liangshen@0.4.4。

     二、现方案（2026-10-31 拍板，已实测生效）
       ★ 已废弃（2026-10-31 晚）：liangshen 已从 profile bundles 移除，纪律改走标准模式（宿主 agent-instructions 的 user 角色基线）。本节仅作历史留档，**不要**再照着改 preset。
       走**系统提示词**通道：`instructionSource: system-prompt`。
       ★ 实测更正：**profile 补丁层那条不生效**（cordis.patch.yml 里加了 id=minimal-prompt 覆盖后，
         重启仍出现 <system-reminder>Updated instructions from… 注入 ⇒ 纪律还在走消息通道）。
         真正生效的是直接改 preset 的配置行：
           node_modules/@linxin666/dsh-liangshen/presets/liangshen/agent.cordis.yml
             L161: instructionSource: host → system-prompt   （25,812 → 25,821 B，其余一字未动）
       生效证据（2026-10-31 12:55 重启后）：
         · 启动 12:55:33 晚于 preset mtime 12:45:03（证明加载）
         · 纪律内容改由 minimal-prompt 以 **workspace-instructions 段**并入系统提示词；
           段首导语即 minimal-prompt.mjs L319 的原文（"They are standing guidance about the
           environment and workspace conventions, not per-task instructions…"）
         · baseline 注入（每轮那条 <system-reminder>Instructions from…）消失；内容改为在提示词里
           以一个"workspace-instructions"块出现（块首即 L319 导语，块内含全局 + 项目两份文件）
         · 注意：**编辑 AGENTS.md 后宿主仍会推一条** <system-reminder>Updated instructions from… ——
           那是"文件已变，请用新内容"的变更通知，不是 baseline 注入，属正常行为（勿当成回退）
       代价：preset 在 node_modules 里，插件升级会被覆盖 ⇒ 升级后需重做这一步（或届时重试补丁层）。
       备份：<你的项目路径>\data\tmp\p532\backup\（cordis.patch.yml 与 preset 改前副本）
             <你的项目路径>\data\tmp\p534\preset_before_edit.yml（preset 改前字节级）
       回滚：删掉补丁里那 6 行（含注释）→ 重启；或把备份 copy 回 cordis.patch.yml。
       验证：① 重启时间晚于 patch mtime（证明加载）② user 段不再出现 `Instructions from: ~/.dsh/AGENTS.md`
             注入块 ③ 启动后无 error/warn 日志 ④ 项目 selftest 51/51。

     三、更正一处此前的错误说法
       "host 模式不抗压缩"是错的：host 模式的 baseline 由宿主**每步重新推导**
       （minimal-prompt.mjs 注释原文 "a message the host re-derives on every step"），
       压缩后下一步会重新注入。改成 system-prompt 的真实收益是三条：
       ① system 角色（服从度更高）② 不占消息位 ③ 与 harness 自身的同类注入去重。

     四、判据的已知局限（2026-10-31 更正，替代原「只能间接判」结论）
       旧记录说"会话转储**不保存**系统提示词 ⇒ 只能间接判"——**错**，已实测推翻。
       v4 转储（~/.dsh/sessions/<ws>/<sid>/session.v4.jsonl.zstd）有独立记录 `system/message`，
       存整份系统提示词（实测 15,201 字符），可**逐字**判；`request/header` 只存 config+tools，不含它。
       读法：多帧 zstd 追加 ⇒ 直接 zstdDecompressSync 只出第一帧，须按魔数 28 B5 2F FD 切帧后逐帧解
       （已封装为 tools/session_forensics.mjs）。
       角色必须分清：liangshen 的 system-prompt 模式纪律在 **system** 段；标准模式（宿主
       agent-instructions）纪律是一条 **user 角色**基线消息，system 提示词里本来就没有它 ——
       在 system 里搜不到纪律，不等于纪律丢了。

     五、预算数字（沿用）
       instructionMaxBytes=65536；7 份 skill 全文 124,939 B ≈ 34k token（全文常驻不可行）；本摘要 ≈1.3k token。
