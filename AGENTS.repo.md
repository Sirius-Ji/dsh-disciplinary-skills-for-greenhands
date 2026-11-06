# 工作纪律摘要（全局·跨项目常驻）

> 每条都来自真实事故；与其它文档冲突时以本文件为准，细节按行末 skill 名深读。**报告失败优于报告成功。**

## 一、执行卫生（每轮都适用）
- 写完被调用的文件，**先确认它存在**再执行；失败先怀疑调用姿势（路径/参数/环境）。(详见 skill: agent-execution-hygiene)
- 重定向/写文件前先建目录；**命令输出为空 = 失败**，不许当成通过。(详见 skill: agent-execution-hygiene)
- **要逐字节/逐字符比 ⇒ 走 Python bytes 层**：shell 重定向与文本 API 会静默改写（PowerShell **5.1** 的 `>` 写 UTF-16（**PS7 是 UTF-8 无 BOM**）、文本 API 做**行尾翻译**（Win: `write_text` 把 `\n`→`\r\n`）、`Get-Content` 走 GBK、`cmd /c` 吃 `^`、**here-string / `-c` 塞代码会吃引号、静默改语义**）；写完先看前 8 字节。(详见 skill: agent-execution-hygiene)
- **编译/语法通过 ≠ 能运行**：改完必须真跑一次（NameError 都在编译绿之后发生）。(详见 skill: agent-execution-hygiene)
- 从邻近代码复制逻辑时，先扫一遍**不属于当前作用域的名字**（孤儿累加器）。(详见 skill: agent-execution-hygiene)

## 二、完成与证据（交付前必过）
- 一次提交=一次门禁：**提交前后各跑一次**，别用未提交的文件骗过门禁。(详见 skill: change-verification-with-evidence)
- 「完成」= 四段式：目标断言改前必红改后必绿 · 回归仍绿 · 外部可复核物证 · 提交后复跑。(详见 skill: change-verification-with-evidence)
- 每条证据都要能回答「**如果我没改会怎样**」；只报后一个数字等于没证据。(详见 skill: change-verification-with-evidence)
- 集合类改动**比内容指纹，不比总数**（总数持平可能掩盖"删一批+加一批"）；删除走可恢复路径并报告从哪拿回来。(详见 skill: change-verification-with-evidence)
- **交付前强制自省「收尾三问」**：① `HANDOFF.md` 更新了吗、有没有写入当前版本号？② `ARCHIVE.md` 追加了吗、`ARCHIVE_INDEX.md` 的锚点与行号回填了吗？③ 有没有够格沉淀成 skill 的教训（结论可以是「无」，但必须写出来）？**三问有一问答不上，就不算交付。**(详见 skill: session-handoff)

## 三、止损与回退（卡住时立刻用）
- 门禁红 **且** 会退化已发布效果 ⇒ **立刻回滚**；可逆的成本远低于"先留着"。(详见 skill: when-to-rollback-or-not-change)
- 同一处**第 3 个补丁**还不成、或补丁须靠"保护性前置"才不崩（白名单/哨兵/跳过）⇒ 说明**改错了层**，停下回架构层。(详见 skill: when-to-rollback-or-not-change)
- 修完指标**反而更差**（残留 2→8）⇒ 立刻回退，**不要叠加**。(详见 skill: when-to-rollback-or-not-change)
- 任何"替换/包裹/转义"先自检**幂等性**：`f(f(x)) == f(x)`，并用真实语料验。(详见 skill: when-to-rollback-or-not-change)
- 「不改」也是决定：必须留**理由 + 当时数字 + 触发条件**，否则会被反复重提。(详见 skill: when-to-rollback-or-not-change)

## 四、测量与病根
- 指标必须**只对目标敏感**：喂它一个已知合格样本，它不能报警。(详见 skill: when-measurement-lies)
- **前置条件缺失 = 假通过**："这个绿能证明被测代码真的跑了吗？"答不上来就不算数。(详见 skill: when-measurement-lies)
- 修完一处**全仓搜同款**：同一根因常在多个落点复发（已踩过 2 次）。(详见 skill: recurring-root-cause-atlas)

## 五、交接与归档（强制项，无前置条件）
- **`HANDOFF.md` 是强制项，不存在也必须创建**：开工第一动作是读它（不是读 `ARCHIVE.md`）；**每个任务收尾或里程碑后必须更新它并写入当前版本号，文件不存在就立刻创建骨架**，不许以「本工作区还没有它」为由跳过；**开发中心固定为 `<你的主库路径>`，交接三件套只在那里；`~/.dsh` 是纯运行环境，禁止产生任何交接文件**；`ARCHIVE.md` **只追加不重写**，**禁止整读**，追溯先看 `ARCHIVE_INDEX.md` 再按锚点 grep。(详见 skill: session-handoff)

## 六、技能进化（评估强制，写盘权人工）
- **每次发版或重大修复完成后，必须强制评估一次是否需要沉淀技能或纪律（触发参考：同一坑踩 3 次 / 重大事故修复 / 重复动作 3 次 / 通用工作流被长期复用 / 你纠正了我）；允许结论是「无」，但必须在交付报告里明确写出评估结果；判定为「需要」时只准在对话里打印草案；未得到你明确的"准入"字样前，一个字节都不许写盘。** 改技能与纪律**只改 D 盘主库**，改完跑 `tools/sync-to-runtime.py` 单向覆盖运行端并核验；`AGENTS.md` 只收纪律，不收技能目录。(详见 skill: skill-evolution)

## 七、高危变更与全链路影响面
- **★ 核心结构文件重命名/移动规范**：`AGENTS.md`、SKILL 模板等核心文件的路径或文件名变更，**落盘前必须先产出《全链路影响面清单》**（同步脚本白名单、pre-commit 钩子、同步校验逻辑、Git 提交触发条件、文档里写死的路径）；清单没理清、没经人过目，一律不许动手改名。此类改动属通道级，同样要过 user 角色验证与压缩存活测试。(详见 skill: skill-evolution)
- **绝对禁止向任何外网/公网（如 GitHub、Gitee 等）执行 git push。**本机已无裸库、无镜像，日常开发只有本地提交，不需要任何推送；`~/.dsh` 里连 Git 都没有。
- **★ 开发中心与运行环境分离（2026-11-06 定案）**：唯一 Git 主库固定在 `<你的主库路径>\skills`；`~/.dsh\skills` 与 `~/.dsh\AGENTS.md` 是**纯运行产物**——禁止在其中执行任何 Git 操作、禁止手改技能、禁止生成交接文件；同步方向**永远 D → C，单向**，在 C 盘改的内容下次同步必被整目录覆盖。(详见 skill: skill-evolution)
