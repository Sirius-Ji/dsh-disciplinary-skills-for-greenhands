#!/usr/bin/env node
/**
 * verify_discipline_channel.mjs —— AGENTS.md 指令通道的运行态断言器（v2）
 *
 * ---------------------------------------------------------------------------
 * v2 修掉的假绿（2026-11-02 实测抓现行）：
 *   v1 用 `inj[inj.length - 1]` 取「最新的 agent-instructions 记录」，**不看 change.path**。
 *   当工作区里同时存在两个指令文件（根 `~/.dsh/AGENTS.md` 与嵌套 `skills/AGENTS.md`）时，
 *   同一会话先后两次运行，v1 分别选中了 seq=2495（根）与 seq=2518（嵌套），**两次都判 PASS**。
 *   这意味着：若压缩后只重注入了嵌套文件、根文件那条丢了，v1 依然会打 ✓ D 并给绿 —— 假绿。
 *
 * v2 策略：
 *   1. 主判定（A/B/C/D）**只作用于根通道** `~/.dsh/AGENTS.md`（可用 --agents 覆盖）；
 *   2. 其它 agent-instructions 路径一律列为「附加通道」，只展示、不参与判定；
 *   3. D 断言必须对**根通道**单独成立，不允许被嵌套文件的记录顶替；
 *   4. 若只存在嵌套注入、根通道一条都没有 ⇒ 退出码 2（无法判定），**绝不能给绿**。
 *
 * 背景：端② 的仓库根文件已改名为 AGENTS.repo.md，宿主不再把它当指令文件，
 *       因此新会话里应当**只剩一条**注入通道。
 *
 * 断言：
 *   A. 根通道最新注入的 role === "user"
 *   B. 该注入 changes[0].digest === 磁盘 AGENTS.md 的 SHA-1
 *   C. 该注入正文逐字符包含磁盘全文（无截断、无改写）
 *   D. 压缩存活：`compaction/end` 之后必须仍有**根通道**的注入
 *
 * 退出码：0 = 通过；1 = 失败；2 = 无法判定（无转储 / 根通道无注入 / 未压缩却要求必测）
 *
 * 用法：
 *   node verify_discipline_channel.mjs
 *   node verify_discipline_channel.mjs --require-compaction
 *   node verify_discipline_channel.mjs --session 2fc7a869
 *   node verify_discipline_channel.mjs --sessions <dir> --agents <file>
 *   node verify_discipline_channel.mjs --cross-session
 */
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import zlib from "node:zlib";
import crypto from "node:crypto";

function argOf(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
const has = (name) => process.argv.includes(name);

const HOME = os.homedir();
const SESSIONS = argOf("--sessions", path.join(HOME, ".dsh", "sessions"));
const AGENTS = argOf("--agents", path.join(HOME, ".dsh", "AGENTS.md"));
const REQUIRE_COMPACTION = has("--require-compaction");
const CROSS = has("--cross-session");
const SESSION_FILTER = argOf("--session", null);

// 相对路径的基准 = 生效端 AGENTS.md 所在目录（即工作区根）
const WS = path.dirname(AGENTS);

const out = [];
const say = (s = "") => out.push(s);

// ---------- 工具 ----------
function collectDumps(dir, acc = []) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return acc; }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) collectDumps(p, acc);
    else if (e.name.includes("session") && e.name.endsWith(".jsonl.zstd")) acc.push(p);
  }
  return acc;
}

function readRecords(file) {
  const buf = fs.readFileSync(file);
  const MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]);
  const starts = [];
  let at = buf.indexOf(MAGIC);
  while (at >= 0) { starts.push(at); at = buf.indexOf(MAGIC, at + 4); }
  const chunks = [];
  for (let i = 0; i < starts.length; i++) {
    const lo = starts[i], hi = i + 1 < starts.length ? starts[i + 1] : buf.length;
    try { chunks.push(zlib.zstdDecompressSync(buf.subarray(lo, hi))); } catch { /* 坏帧跳过 */ }
  }
  const lines = Buffer.concat(chunks).toString("utf8").split(/\r?\n/).filter((l) => l.trim());
  const recs = [];
  for (const l of lines) { try { recs.push(JSON.parse(l)); } catch { /* 坏行跳过 */ } }
  return recs;
}

function collectText(n, acc = []) {
  if (n == null) return acc;
  if (typeof n === "string") { acc.push(n); return acc; }
  if (Array.isArray(n)) { for (const x of n) collectText(x, acc); return acc; }
  if (typeof n === "object") {
    for (const [k, v] of Object.entries(n)) {
      if (k === "text" && typeof v === "string") acc.push(v);
      else if (typeof v === "object") collectText(v, acc);
    }
  }
  return acc;
}

const injectionsOf = (recs) => recs.filter((r) => r.data?.source?.kind === "agent-instructions");
const compactionsOf = (recs) => recs.filter((r) => /^compaction\//.test(r.type || ""));
const rawPathOf = (r) => ((r.data?.source?.changes || [])[0] || {}).path;

// ---------- 路径归一化（v2 的核心）----------
function absOf(p) {
  if (typeof p !== "string" || !p.trim()) return null;
  let s = p.trim().replace(/\\/g, "/");
  if (s === "~") return path.resolve(HOME);
  if (s.startsWith("~/")) return path.resolve(path.join(HOME, s.slice(2)));
  if (path.isAbsolute(s)) return path.resolve(s);
  return path.resolve(path.join(WS, s)); // 相对路径 = 相对工作区根
}

const keyOf = (r) => {
  const a = absOf(rawPathOf(r));
  return a ? a.toLowerCase() : "<no-path>";
};
const ROOT_KEY = path.resolve(AGENTS).toLowerCase();
const isRootInj = (r) => keyOf(r) === ROOT_KEY;

function channelTable(inj) {
  const map = new Map();
  for (const r of inj) {
    const raw = rawPathOf(r);
    const k = keyOf(r);
    if (!map.has(k)) {
      map.set(k, { raw, abs: absOf(raw), count: 0, lastSeq: 0, root: k === ROOT_KEY });
    }
    const e = map.get(k);
    e.count++;
    const seq = r.seq || 0;
    if (seq >= e.lastSeq) { e.lastSeq = seq; e.lastBaseline = r.data?.source?.baseline; }
    if (!e.raw && raw) e.raw = raw;
  }
  return [...map.values()].sort((a, b) => b.lastSeq - a.lastSeq);
}

// ---------- 前置 ----------
if (!fs.existsSync(AGENTS)) {
  say(`✗ 找不到生效端 AGENTS.md：${AGENTS}`);
  console.log(out.join("\n"));
  process.exit(2);
}
const diskBytes = fs.readFileSync(AGENTS);
const diskText = diskBytes.toString("utf8");
const diskSha1 = crypto.createHash("sha1").update(diskBytes).digest("hex");

let dumps = collectDumps(SESSIONS)
  .map((f) => ({ f, m: fs.statSync(f).mtimeMs }))
  .sort((a, b) => b.m - a.m);
if (SESSION_FILTER) dumps = dumps.filter((d) => d.f.includes(SESSION_FILTER));

say("========== verify_discipline_channel (v2) ==========");
say(`生效端 AGENTS.md : ${diskBytes.length} B  chars=${diskText.length}  sha1=${diskSha1}`);
say(`根通道（主判定） : ${path.resolve(AGENTS)}`);
say(`工作区根         : ${WS}`);
say(`会话目录         : ${SESSIONS}`);
say(`找到转储         : ${dumps.length} 个${SESSION_FILTER ? `（已按 --session ${SESSION_FILTER} 过滤）` : ""}`);

if (!dumps.length) {
  say("");
  say("✗ 无法判定：没有任何会话转储");
  console.log(out.join("\n"));
  process.exit(2);
}

const target = dumps[0].f;
const recs = readRecords(target);
const inj = injectionsOf(recs);
const rootInj = inj.filter(isRootInj);
const comps = compactionsOf(recs);
const compEnds = comps.filter((c) => c.type === "compaction/end");

say("");
say("--- 目标会话 ---");
say(`文件        : ${path.basename(path.dirname(target))}`);
say(`记录        : ${recs.length}（转储是活文件，此数只代表本次读取瞬间）`);
say(`注入记录    : ${inj.length} 条（其中根通道 ${rootInj.length} 条）`);
say(`压缩事件    : ${comps.length}（compaction/end ${compEnds.length} 次）`);

if (!inj.length) {
  say("");
  say("✗ 无法判定：该会话没有任何 agent-instructions 注入记录");
  console.log(out.join("\n"));
  process.exit(2);
}

// ---------- v1 的坑：根通道一条都没有，绝不给绿 ----------
if (!rootInj.length) {
  say("");
  say("--- 附加通道清单（仅供定位，不参与判定）---");
  for (const c of channelTable(inj)) {
    say(`  seq最晚=${String(c.lastSeq).padEnd(6)} 注入${String(c.count).padEnd(3)}次  ${JSON.stringify(c.raw)}`);
  }
  say("");
  say("✗ 无法判定：根通道没有任何注入记录（其它路径的记录不能顶替）");
  say("  这正是 v1 的假绿来源：嵌套文件的注入会被误当成 AGENTS.md 通道。");
  console.log(out.join("\n"));
  process.exit(2);
}

let failed = 0;
let skipped = 0;

const latest = rootInj[rootInj.length - 1];
const src = latest.data.source || {};
const change = (src.changes || [])[0] || {};
const body = collectText(latest.data.content, []).join("");
const at = body.indexOf(diskText);
const prefix = at >= 0 ? body.slice(0, at) : "";
const suffix = at >= 0 ? body.slice(at + diskText.length) : "";

say("");
say("--- A/B/C. 根通道最新注入 ---");
say(`seq             : ${latest.seq}`);
say(`change.path     : ${JSON.stringify(change.path)}`);
say(`role            : ${JSON.stringify(latest.data.role)}`);
say(`source.baseline : ${JSON.stringify(src.baseline)}`);
say(`change.action   : ${JSON.stringify(change.action)}`);
say(`成文长度        : ${body.length} 字符`);
say(`三段核算        : 前缀 ${prefix.length} + 正文 ${diskText.length} + 后缀 ${suffix.length} = ${prefix.length + diskText.length + suffix.length}`);

say("");
if (latest.data.role === "user") {
  say('✓ A. role === "user"');
} else {
  say(`✗ A. role 不是 user，实际为 ${JSON.stringify(latest.data.role)}`);
  failed++;
}

if (change.digest === diskSha1) {
  say("✓ B. digest === 磁盘 SHA-1");
} else {
  say(`✗ B. digest 不匹配：记录 ${change.digest} / 磁盘 ${diskSha1}`);
  failed++;
}

if (body.includes(diskText)) {
  say("✓ C. 正文逐字符包含磁盘全文");
} else {
  say(`✗ C. 正文未完整包含磁盘全文（可能截断或被改写，全文起始位置=${at}）`);
  failed++;
}

// ---------- D. 压缩存活（只认根通道）----------
say("");
say("--- D. 压缩存活（仅根通道算数）---");
if (!compEnds.length) {
  if (REQUIRE_COMPACTION) {
    say("✗ D. 本会话尚未压缩，且指定了 --require-compaction ⇒ 无法判定");
  } else {
    say("⊘ D. SKIP：本会话尚未发生压缩（不等于通过）");
    say("     要实测请执行 /compact，然后重跑本脚本（或加 --require-compaction 强制必测）");
  }
  skipped++;
} else {
  const lastEnd = Math.max(...compEnds.map((c) => c.seq || 0));
  const afterRoot = rootInj.filter((r) => (r.seq || 0) > lastEnd);
  say(`最后一次 compaction/end : seq=${lastEnd}`);
  say(`其后根通道注入          : ${afterRoot.length} 条`);
  if (afterRoot.length) {
    for (const a of afterRoot) {
      const ad = (a.data.source?.changes || [])[0] || {};
      say(`  seq=${a.seq}  role=${a.data.role}  action=${JSON.stringify(ad.action)}  baseline=${JSON.stringify(a.data.source?.baseline)}  digest=${String(ad.digest).slice(0, 12)}`);
    }
    say("✓ D. 压缩后根通道重新注入了基线");
  } else {
    say("✗ D. 压缩后根通道没有任何注入 —— 压缩可能吃掉纪律");
    say("     （注：若此时只有嵌套文件的注入，v1 会误判为通过）");
    failed++;
  }
}

// ---------- 注入通道清单 ----------
say("");
say("--- 注入通道清单（★ = 主判定通道）---");
let extraLive = 0;
for (const c of channelTable(inj)) {
  const exists = c.abs && fs.existsSync(c.abs);
  const mark = c.root ? "★" : " ";
  const flag = c.root ? "根通道" : exists ? "附加·文件仍在" : "附加·文件已不存在（历史记录）";
  if (!c.root && exists) extraLive++;
  say(`${mark} seq最晚=${String(c.lastSeq).padEnd(6)} 注入${String(c.count).padEnd(3)}次  ${JSON.stringify(c.raw)}`);
  say(`    ${flag}   实际路径=${c.abs || "?"}   文件存在=${exists}`);
}
if (extraLive) {
  say("");
  say(`  ⚠ 仍有 ${extraLive} 个附加通道的文件存在于磁盘 —— 宿主可能继续双注入`);
  say("     处置：确认该文件是否应叫 AGENTS.md；端② 仓库根应叫 AGENTS.repo.md");
} else {
  say("");
  say("  ✓ 除根通道外，没有任何仍然存在的附加指令文件（改名已生效）");
}

// ---------- 跨会话机制证据 ----------
if (CROSS) {
  say("");
  say("--- 跨会话机制证据（压缩 -> 根通道重注入）---");
  let withBoth = 0, survived = 0;
  for (const { f } of dumps) {
    let r;
    try { r = readRecords(f); } catch { continue; }
    const ce = compactionsOf(r).filter((c) => c.type === "compaction/end");
    const ri = injectionsOf(r).filter(isRootInj);
    if (!ce.length || !ri.length) continue;
    withBoth++;
    const last = Math.max(...ce.map((c) => c.seq || 0));
    const after = ri.filter((x) => (x.seq || 0) > last);
    const ok = after.length > 0;
    if (ok) survived++;
    say(`  ${path.basename(path.dirname(f)).slice(0, 12)}  压缩${ce.length}次  根通道重注入=${ok ? "是" : "否"}`);
  }
  say(`  小结：${survived}/${withBoth} 个"既注入过又压缩过"的会话在压缩后重注入根通道`);
  if (withBoth && survived < withBoth) failed++;
}

say("");
const verdict = failed ? "✗ FAIL" : skipped ? "⊘ SKIP（不得当绿）" : "✓ PASS";
say(`结论：${verdict}`);
say(`退出码：${failed ? 1 : skipped ? 2 : 0}`);
console.log(out.join("\n"));
process.exit(failed ? 1 : skipped ? 2 : 0);
