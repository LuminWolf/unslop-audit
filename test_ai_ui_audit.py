#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_ui_audit.py（unslop 对齐修复版）的验收测试。

101 个 HTML / CSS 片段逐条写入临时文件，调用修复版 scan_file() 取真实命中。

用例分类（沿用对齐性审计阶段的 ID 与源码，语义已翻转成"修复后必须通过"）：
  positive  : SKILL 禁止 → 必须命中 expect 里的规则
  allowed   : SKILL 允许 → 必须零命中
  gap       : 修复前漏检 → 现在必须至少命中一条
  overreach : 修复前误报 → 现在必须零命中
  dead      : 修复前死规则 → 现在必须命中 expect 里的规则

运行：
    python3 test_ai_ui_audit.py
    AUDIT_SCRIPT=/path/to/other/ai_ui_audit.py python3 test_ai_ui_audit.py
"""

import atexit
import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
from dataclasses import dataclass, field
from pathlib import Path

warnings.simplefilter("ignore")

HERE = Path(__file__).resolve().parent
AUDIT_SCRIPT = os.environ.get("AUDIT_SCRIPT", str(HERE / "ai_ui_audit.py"))


def _subprocess_env():
    """显式给子进程开 UTF-8，避免 Windows 默认 GBK 解码子进程输出。"""

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


_spec = importlib.util.spec_from_file_location("ai_ui_audit_under_test", AUDIT_SCRIPT)
AUDIT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AUDIT)

_TMP = tempfile.mkdtemp(prefix="unslop-audit-test-")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)


@dataclass
class Case:
    id: str
    section: str
    kind: str            # positive / allowed / gap / overreach / dead
    source: str
    skill_says: str
    expect: set = field(default_factory=set)
    ext: str = "html"


CASES = [
    # Spacing
    Case("S01", "1 Spacing", "dead", '<div class="mt-[13px]">x</div>',
         'Remove one-off values that break the rhythm, like mt-[13px]（SKILL 原文举例）',
         {"arbitrary-spacing"}),
    Case("S02", "1 Spacing", "dead", '<div class="py-[11px]">x</div>',
         'Remove one-off values that break the rhythm, like py-[11px]（SKILL 原文举例）',
         {"arbitrary-spacing"}),
    Case("S08", "1 Spacing", "positive", '<div class="p-[13px]">x</div>',
         'Remove one-off values that break the rhythm（无方向后缀形式才可触发）',
         {"arbitrary-spacing"}),
    Case("S03", "1 Spacing", "positive", '<style>.a { margin: 13px; }</style>',
         'Everything sits on a 4px grid. Margins ... are multiples of 4',
         {"css-spacing-off-grid"}, ext="css"),
    Case("S04", "1 Spacing", "positive", '<style>.a { padding: 13px; }</style>',
         'Everything sits on a 4px grid. ... paddings ... are multiples of 4',
         {"css-spacing-off-grid"}, ext="css"),
    Case("S05", "1 Spacing", "positive", '<style>.a { gap: 13px; }</style>',
         'Everything sits on a 4px grid. ... gaps ... are multiples of 4',
         {"css-gap-off-grid"}, ext="css"),
    Case("S06", "1 Spacing", "positive", '<style>.a { column-gap: 13px; }</style>',
         'Everything sits on a 4px grid. ... gaps ... are multiples of 4',
         {"css-gap-off-grid"}, ext="css"),
    Case("S07", "1 Spacing", "positive", '<style>.a { transform: translateY(3px); }</style>',
         'Nothing is nudged off the line with a stray translate or odd margin',
         {"translate-tweak"}, ext="css"),
    Case("A01", "1 Spacing", "allowed", '<style>.a { padding: 28px; gap: 104px; }</style>',
         '28 or 104 are fine even though they are not in the token list', ext="css"),
    Case("O01", "1 Spacing", "overreach", '<button style="padding: 2px">+</button>',
         'A 2px step is fine for nudges inside small controls'),
    Case("G01", "1 Spacing", "gap", '<div style="padding: 16px 13px">x</div>',
         'Everything sits on a 4px grid（多值声明的第二个值同样受约束）'),
    Case("G02", "1 Spacing", "gap", '<div style="height: 37px">x</div>',
         'Margins, paddings, gaps and fixed heights are multiples of 4'),
    Case("G03", "1 Spacing", "gap", '<div style="margin-top: 13px">x</div>',
         'Margins ... are multiples of 4（方向后缀写法）'),
    Case("G04", "1 Spacing", "gap", '<div style="gap: 16px 13px">x</div>',
         'Gaps ... are multiples of 4（多值声明）'),

    # Color
    Case("C01", "2 Color", "positive", '<div class="from-purple-500 to-violet-500"></div>',
         'Remove hue gradients on surfaces', {"tw-purple-gradient"}),
    Case("C02", "2 Color", "positive",
         '<style>.h { background: linear-gradient(135deg, #a855f7, #8b5cf6); }</style>',
         'Never from one hue to another', {"css-purple-gradient"}, ext="css"),
    Case("C03", "2 Color", "positive",
         '<style>.h { box-shadow: 0 0 24px #a855f7; }</style>',
         'Remove colored glows and colored shadows', {"colored-shadow"}, ext="css"),
    Case("C04", "2 Color", "positive", '<div class="backdrop-blur-[20px]"></div>',
         'Remove glass / glassmorphism（Do not 段）', {"glass-blur"}),
    Case("C05", "2 Color", "dead",
         '<div class="bg-gradient-to-r from-cyan-500 to-purple-500"></div>',
         'Remove hue gradients on surfaces（青→紫是 SKILL description 点名的迹象）',
         {"rainbow-gradient"}),
    Case("C06", "2 Color", "dead", '<style>.h { border: 1px solid #a855f7; }</style>',
         'Remove ... neon borders', {"neon-border"}, ext="css"),
    Case("C07", "2 Color", "positive",
         '<style>.h { background: radial-gradient(circle, #a855f7, transparent); }</style>',
         'Remove ... radial color washes', {"radial-or-fixed-bg"}, ext="css"),
    Case("C08", "2 Color", "positive", '<style>.h { background-attachment: fixed; }</style>',
         'Remove motion ... parallax（§9，脚本归入颜色维度）', {"radial-or-fixed-bg"}, ext="css"),
    Case("C09", "2 Color", "positive", '<div class="bg-gradient-to-r"></div>',
         'Remove hue gradients on surfaces', {"tw-gradient-class"}),
    Case("A02", "2 Color", "allowed",
         '<style>.row { background: linear-gradient(#2b2b2b, #1f1f1f); }</style>',
         'A gradient is allowed only as a small tone shift inside one neutral', ext="css"),
    Case("G05", "2 Color", "gap",
         '<style>.h { background: linear-gradient(135deg, #6366f1, #06b6d4); }</style>',
         'Never from one hue to another（CSS 版 indigo→cyan，非 Tailwind 类名）', ext="css"),
    Case("G06", "2 Color", "gap",
         '<style>.h { box-shadow: 0 0 24px rgba(168, 85, 247, .45); }</style>',
         'Remove colored glows and colored shadows（rgba 写法）', ext="css"),
    Case("G07", "2 Color", "gap", '<style>body { background-color: #a855f7; }</style>',
         'A screen whose background reads as ... blue ... has gone too far', ext="css"),
    Case("G08", "2 Color", "gap",
         '<style>.h { border: 1px solid rgba(168, 85, 247, .6); }</style>',
         'Remove ... neon borders（rgba 写法）', ext="css"),
    Case("G09", "2 Color", "gap", '<style>.h { backdrop-filter: blur(8px); }</style>',
         'Remove glassmorphism（最常见写法 + 单位数 blur）', ext="css"),
    Case("O07", "2 Color", "overreach",
         '<div class="bg-gradient-to-r from-gray-900 to-gray-800"></div>',
         'A gradient is allowed ... inside one neutral（同色明度渐变被无条件判 HIGH）'),

    # Icons
    Case("I01", "3 Icons", "positive", '<span>New ✨</span>',
         'Every emoji used as an icon or as decoration in a label becomes a line icon',
         {"label-emoji", "emoji-as-icon"}),
    Case("I02", "3 Icons", "positive", '<span>Beta 🚀</span>',
         'Badges like New ✨ or Beta 🚀 go away', {"label-emoji", "emoji-as-icon"}),
    Case("I03", "3 Icons", "positive", '<span>Hot ⭐</span>',
         'Every emoji used as ... decoration in a label', {"label-emoji"}),
    Case("I04", "3 Icons", "positive", '<span>💡 Tip</span>',
         'No emoji left in the interface（非 label 场景由兜底扫描命中）',
         {"emoji-as-icon"}),
    Case("A06", "3 Icons", "allowed",
         '<svg width="18" height="18" stroke-width="1.5" viewBox="0 0 24 24"></svg>',
         'One size and one stroke everywhere, 16 or 18px with a 1.5 stroke'),
    Case("G10", "3 Icons", "gap", '<span>⭐</span>',
         'No emoji left in the interface（U+2B50 不在兜底扫描的字符区间内）'),
    Case("G11", "3 Icons", "gap",
         '<svg width="16" stroke-width="2"></svg><svg width="24" stroke-width="1"></svg>',
         'One size and one stroke everywhere（尺寸/描边不一致）'),

    # Copy
    Case("P01", "4 Copy", "positive", '<h1>Welcome back, Damir! 👋</h1>',
         'No greeting headlines like Welcome back, Damir! 👋',
         {"greeting", "emoji-as-icon"}),
    Case("P02", "4 Copy", "positive", '<h2>Supercharge your workflow</h2>',
         'No hype words like supercharge, seamless, unlock, magic, revolutionize',
         {"marketing-words"}),
    Case("P03", "4 Copy", "positive", '<h2>Revolutionize reporting</h2>',
         'No hype words ... revolutionize', {"marketing-words"}),
    Case("P04", "4 Copy", "positive", '<span>AI-powered analytics</span>',
         'no AI-powered on everything', {"ai-powered"}),
    Case("P05", "4 Copy", "positive", '<span>AI powered search</span>',
         'no AI-powered on everything（无连字符写法）', {"ai-powered"}),
    Case("P06", "4 Copy", "positive", '<p>Loved by 10,000+ teams</p>',
         'Claims that cannot be checked, like Loved by 10,000+ teams',
         {"social-proof"}),
    Case("P07", "4 Copy", "positive", '<p>Trusted by 5,000+ companies</p>',
         'Claims that cannot be checked', {"social-proof"}),
    Case("P08", "4 Copy", "positive", '<p>10x faster</p>',
         'Claims that cannot be checked, like ... 10x faster', {"hype-number"}),
    Case("P09", "4 Copy", "positive", '<p>Ship it!!</p>',
         'never !!', {"multi-bang"}),
    Case("P10", "4 Copy", "positive", '<p>John Doe</p>',
         'Mock data looks real, with plausible numbers and names',
         {"placeholder-data"}),
    Case("P11", "4 Copy", "positive", '<p>lorem ipsum dolor</p>',
         'Mock data looks real（占位文本）', {"placeholder-data"}),
    Case("P12", "4 Copy", "positive", '<p>Acme Corp</p>',
         'Mock data looks real（占位公司名）', {"placeholder-data"}),
    Case("A05", "4 Copy", "allowed", '<h1>October 2026</h1><p>+12% vs last month</p>',
         'The title names the context ... A change says what it compares to'),
    Case("A07", "4 Copy", "allowed", '<label>Search</label>',
         'Short labels. Search, not Search anything...'),
    Case("O02", "4 Copy", "overreach", '<p>For example, pick a date.</p>',
         'SKILL 只禁止占位假数据，普通英文单词 example 不应被判占位'),
    Case("O08", "4 Copy", "overreach", '<div class="test">x</div>',
         'SKILL 只禁止占位假数据，test 作为类名不应被判占位'),
    Case("G12", "4 Copy", "gap", '<h1>Ship it!</h1>',
         'No exclamation marks in interface text（单个 ! 同样禁止）'),
    Case("G13", "4 Copy", "gap", '<button>Get started.</button>',
         'Headlines, subheads, labels, buttons and captions end without a period'),
    Case("G14", "4 Copy", "gap", '<label>Search anything...</label>',
         'Short labels. Search, not Search anything...'),
    Case("G15", "4 Copy", "gap", '<p>+12%</p>',
         'A change says what it compares to, like +12% vs last month'),

    # Type
    Case("T01", "5 Type", "positive", '<h1 class="font-bold">Title</h1>',
         'No 700 to 900 headings', {"heavy-weight"}),
    Case("T02", "5 Type", "positive", '<style>h1 { font-weight: 800; }</style>',
         'No 700 to 900 headings', {"heavy-weight"}, ext="css"),
    Case("T03", "5 Type", "positive", '<style>.s { letter-spacing: -0.05em; }</style>',
         'Small text never gets negative letter spacing', {"negative-tracking"}, ext="css"),
    Case("T04", "5 Type", "positive", '<div class="tracking-[wide]">PAID</div>',
         'no uppercase tracked labels', {"wide-tracking"}),
    Case("T05", "5 Type", "positive", '<style>.s { letter-spacing: 0.5em; }</style>',
         'no uppercase tracked labels', {"wide-tracking"}, ext="css"),
    Case("T06", "5 Type", "positive", '<style>.s { text-transform: uppercase; }</style>',
         'Sentence case everywhere', {"uppercase-label"}, ext="css"),
    Case("T07", "5 Type", "positive", '<style>.s { color: transparent; }</style>',
         'no gradient text', {"gradient-text"}, ext="css"),
    Case("T08", "5 Type", "positive", '<style>.s { -webkit-text-fill-color: transparent; }</style>',
         'no gradient text', {"gradient-text"}, ext="css"),
    Case("T09", "5 Type", "positive", '<h1 class="bg-clip-text text-transparent">Hi</h1>',
         'no gradient text', {"tw-gradient-text"}),
    Case("T10", "5 Type", "positive", '<style>.s { font-style: italic; }</style>',
         'No italic for emphasis', {"italic-emphasis"}, ext="css"),
    Case("O03", "5 Type", "overreach", '<style>::placeholder { color: transparent; }</style>',
         'SKILL 禁的是 gradient text；任何 color: transparent 都被判 CRITICAL 定性过宽',
         ext="css"),
    Case("O04", "5 Type", "overreach", '<style>/* italic hint */ .a { color: red; }</style>',
         'SKILL 禁的是 italic 强调；注释里的单词不应命中', ext="css"),
    Case("G16", "5 Type", "gap", '<div class="uppercase tracking-widest">NAVIGATION</div>',
         'Labels like NAVIGATION ... with wide tracking become Navigation'),
    Case("G17", "5 Type", "gap", '<p>$48,210</p><p>$124,860.40</p>',
         'Numbers use tabular-nums and one format across the screen'),

    # Layout
    Case("L01", "6 Layout", "positive",
         '<section class="flex items-center justify-center flex-col text-center"></section>',
         'Everything stacked and centered is the template default',
         {"centered-stack"}),
    Case("L02", "6 Layout", "dead", '<main class="max-w-[400px] mx-auto"></main>',
         'Never shrink an app into a narrow centered column', {"narrow-column"}),
    Case("G18", "6 Layout", "gap",
         '<section class="flex flex-col items-center justify-center text-center"></section>',
         'Everything stacked and centered is the template default（类名顺序不同即漏检）'),
    Case("G19", "6 Layout", "gap", '<main class="max-w-md mx-auto"></main>',
         'Never shrink an app into a narrow centered column（Tailwind 具名尺度）'),
    Case("G20", "6 Layout", "gap",
         '<button>Start</button><button>Learn more</button><button>Sign up</button>',
         'One primary action and at most one secondary action next to it'),
    Case("G21", "6 Layout", "gap", '<html lang="ar"><body>لوحة التحكم</body></html>',
         'Checklist: Right to left screens follow rtl.md: dir and lang set ...'),

    # Details
    Case("D01", "7 Details", "positive", '<button class="rounded-full">Go</button>',
         'Not everything is a pill', {"big-radius"}),
    Case("D02", "7 Details", "positive", '<style>.c { border-radius: 24px; }</style>',
         'Nested radius ... cards 12 to 16, panels 14 to 20', {"big-radius"}, ext="css"),
    Case("D03", "7 Details", "dead", '<span class="badge rounded-full">3</span>',
         'Counts and meta become quiet text ... instead of glowing pills',
         {"badge-pill"}),
    Case("A03", "7 Details", "allowed",
         '<style>.btn { border-radius: 8px; } .card { border-radius: 16px; }</style>',
         'Controls 8 to 10, cards 12 to 16', ext="css"),
    Case("A08", "7 Details", "allowed", '<div class="rounded-xl">Card</div>',
         'Controls 8 to 10, cards 12 to 16（rounded-xl=12px 合法）'),
    Case("O06", "7 Details", "overreach", '<div class="rounded-2xl">Card</div>',
         'Cards 12 to 16（rounded-2xl=16px 在允许区间内，却一律被报）'),
    Case("G22", "7 Details", "gap",
         '<div class="stat-card"><svg class="sparkline"></svg></div>',
         'Stat cards are numbers ... No sparklines, tallies, mini bars or icons added to fill them'),

    # Visuals
    Case("V01", "8 Visuals", "positive", '<div class="blob"></div>',
         'Glossy blobs, orbs, nebulas ... say nothing about the product',
         {"decorative-nouns"}),
    Case("V02", "8 Visuals", "positive", '<div class="bg-indigo-600"></div>',
         'The backgrounds ... stay neutral', {"purple-bg"}),
    Case("V03", "8 Visuals", "positive", '<style>.bg { filter: blur(20px); }</style>',
         'Decorative filler goes', {"heavy-blur-filter"}, ext="css"),
    Case("O05", "8 Visuals", "overreach", '<h1>Glow</h1>',
         'Do not rename the product（产品名含装饰词也被判 HIGH）'),
    Case("G27", "8 Visuals", "gap", '<div class="bg-purple-50"></div>',
         'The backgrounds ... stay neutral（浅色紫背景只匹配 100-900 整百档）'),
    Case("G28", "8 Visuals", "gap", '<div class="animate-[float_6s_ease-in-out_infinite]"></div>',
         'Remove motion that loops for no reason ... floating elements'),

    # Motion
    Case("M01", "9 Motion", "positive", '<div class="animate-ping"></div>',
         'Remove motion that loops for no reason, like animate-pulse or animate-ping',
         {"looping-animation"}),
    Case("M02", "9 Motion", "positive", '<div class="transition-all"></div>',
         'Remove transition-all', {"transition-all"}),
    Case("M03", "9 Motion", "positive", '<style>.a { transition: all 200ms ease; }</style>',
         'Remove transition-all', {"transition-all"}, ext="css"),
    Case("M04", "9 Motion", "positive", '<div class="hover:scale-105"></div>',
         'Remove ... hover:scale on cards', {"hover-scale"}),
    Case("M05", "9 Motion", "positive", '<style>.a { animation: float 4s infinite; }</style>',
         'Remove motion that loops for no reason ... floating elements',
         {"long-animation"}, ext="css"),
    Case("M06", "9 Motion", "positive",
         '<style>.a:hover { transform: scale(1.05); }</style>',
         'Remove ... hover:scale on cards', {"hover-scale"}, ext="css"),
    Case("A04", "9 Motion", "allowed",
         '<style>.a { transition: color 150ms ease, background-color 150ms ease; }</style>',
         'Transition color, background, border, opacity and transform, and name them', ext="css"),
    Case("G23", "9 Motion", "gap", '<style>.a { animation: pulse 2s infinite; }</style>',
         'Remove motion that loops for no reason（≤3s 的循环同样要移除）', ext="css"),
    Case("G24", "9 Motion", "gap", '<div class="hover:scale-[1.02]"></div>',
         'Remove ... hover:scale on cards（任意值写法）'),
    Case("G25", "9 Motion", "gap", '<style>.a { transition: width 300ms ease; }</style>',
         'Never animate width, height, top, left, margins or large blurs', ext="css"),
    Case("G26", "9 Motion", "gap", '<style>h1 { animation: shimmer 1.5s infinite linear; }</style>',
         'Remove ... shimmer on headings', ext="css"),
]

def scan_case(case: Case) -> set:
    path = Path(_TMP) / ("%s.%s" % (case.id, case.ext))
    path.write_text(case.source, encoding="utf-8")
    return {f.pattern for f in AUDIT.scan_file(str(path))}


RESULTS = {c.id: scan_case(c) for c in CASES}
BY_ID = {c.id: c for c in CASES}


def _fmt(hits: set) -> str:
    return ", ".join(sorted(hits)) if hits else "-"


def run_cli(args):
    if "--csv" not in args:
        args = args + ["--csv", str(Path(_TMP) / "cli_report.csv")]
    return subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT)] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(HERE), env=_subprocess_env(),
    )


def print_details():
    print("\n" + "=" * 100)
    print("  FIXED BUILD — CASE DETAIL  (actual = 修复版真实命中)")
    print("=" * 100)
    print("%-5s %-11s %-11s %-6s %s" % ("ID", "SECTION", "KIND", "HITS", "ACTUAL"))
    print("-" * 100)
    for c in CASES:
        hits = RESULTS[c.id]
        print("%-5s %-11s %-11s %-6d %s" % (c.id, c.section, c.kind, len(hits), _fmt(hits)))
    print("-" * 100)
    for kind in ("positive", "allowed", "gap", "overreach", "dead"):
        n = sum(1 for c in CASES if c.kind == kind)
        print("  %-10s : %2d cases" % (kind, n))
    print("  rules     : %d (含 emoji-as-icon)" % (len(AUDIT.RULES) + 1))
    print("=" * 100 + "\n")


class FixedBuildTests(unittest.TestCase):

    def test_00_cli_runs_without_crashing(self):
        """P0 验收：脏页不崩，问题写入 CSV，汇总打印到控制台。"""
        r = run_cli(["sample_slop.html"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("SUMMARY", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

        csv_path = Path(_TMP) / "cli_report.csv"
        with csv_path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertTrue(rows)
        self.assertEqual(list(rows[0]), ["path", "line", "problem", "fix"])
        self.assertTrue(all(row["path"].endswith("sample_slop.html") for row in rows))
        self.assertTrue(all(row["line"].isdigit() for row in rows))
        self.assertTrue(all(row["problem"] for row in rows))
        self.assertTrue(all(row["fix"] for row in rows))

    def test_01_positive_cases_hit(self):
        """SKILL 点名禁止的迹象，必须命中（51 个用例）。"""
        bad = []
        for c in CASES:
            if c.kind != "positive":
                continue
            miss = c.expect - RESULTS[c.id]
            if miss:
                bad.append("%s 期望 %s，实际 %s" % (c.id, _fmt(c.expect), _fmt(RESULTS[c.id])))
        self.assertFalse(bad, "\n".join(bad))

    def test_02_allowed_cases_stay_clean(self):
        """SKILL 明确允许的写法，必须零命中（8 个用例）。"""
        bad = ["%s -> %s" % (c.id, _fmt(RESULTS[c.id]))
               for c in CASES if c.kind == "allowed" and RESULTS[c.id]]
        self.assertFalse(bad, "\n".join(bad))

    def test_03_former_gaps_now_detected(self):
        """修复前的 28 处漏检，现在必须至少命中一条规则。"""
        bad = [c.id for c in CASES if c.kind == "gap" and not RESULTS[c.id]]
        self.assertFalse(bad, "仍漏检: %s" % bad)

    def test_04_former_overreach_now_clean(self):
        """修复前的 8 处误报，现在必须零命中。"""
        bad = ["%s -> %s" % (c.id, _fmt(RESULTS[c.id]))
               for c in CASES if c.kind == "overreach" and RESULTS[c.id]]
        self.assertFalse(bad, "\n".join(bad))

    def test_05_former_dead_rules_now_fire(self):
        """修复前的 6 个死规则用例，现在必须命中对应规则名。"""
        bad = []
        for c in CASES:
            if c.kind != "dead":
                continue
            miss = c.expect - RESULTS[c.id]
            if miss:
                bad.append("%s 期望 %s，实际 %s" % (c.id, _fmt(c.expect), _fmt(RESULTS[c.id])))
        self.assertFalse(bad, "\n".join(bad))

    def test_06_no_dead_rules_left(self):
        """所有已声明规则都至少被一个用例触发，不许再出现死规则。"""
        covered = set().union(*RESULTS.values())
        declared = {r.name for r in AUDIT.RULES} | {"emoji-as-icon"}
        self.assertEqual(declared - covered, set(),
                         "无用例能触发: %s" % sorted(declared - covered))

    def test_07_dimension_order_matches_skill_passes(self):
        dims = [d.value.split("-", 1)[1] for d in AUDIT.Dimension]
        self.assertEqual(dims, ["Spacing", "Color", "Icons", "Copy", "Type",
                                "Layout", "Details", "Visuals", "Motion"])

    def test_08_whole_page_scores(self):
        """整页对照：脏页低分、干净页满分，且 JSON 不被 PASS/FAIL 污染。"""
        dirty = run_cli(["sample_slop.html", "--json"])
        self.assertEqual(dirty.returncode, 0, dirty.stderr)
        rd = json.loads(dirty.stdout)
        self.assertGreater(rd["total_findings"], 0)
        self.assertLess(rd["score"], 40)
        self.assertEqual(set(rd["by_dimension"]), {d.value for d in AUDIT.Dimension})

        clean = run_cli(["sample_clean.html", "--json"])
        self.assertEqual(clean.returncode, 0, clean.stderr)
        rc = json.loads(clean.stdout)
        self.assertEqual(rc["total_findings"], 0)
        self.assertEqual(rc["score"], 100)

    def test_09_fail_on_gate(self):
        """--fail-on 作为 CI 门禁：脏页 exit 2，干净页 exit 0，stdout 始终是纯 JSON。"""
        dirty = run_cli(["sample_slop.html", "--json", "--fail-on", "high"])
        self.assertEqual(dirty.returncode, 2)
        self.assertIn("FAIL", dirty.stderr)
        self.assertIsInstance(json.loads(dirty.stdout), dict)  # stdout 未被污染

        clean = run_cli(["sample_clean.html", "--json", "--fail-on", "high"])
        self.assertEqual(clean.returncode, 0)
        self.assertIn("PASS", clean.stderr)
        self.assertIsInstance(json.loads(clean.stdout), dict)

    def test_10_original_build_still_broken(self):
        """对照：随包保留的原始脚本在 pyparsing 3.x 下依旧崩溃。"""
        original = HERE / "reference" / "ai_ui_audit.original.py"
        if not original.exists():
            self.skipTest("原始脚本不在包内")
        r = subprocess.run(
            [sys.executable, str(original), str(HERE / "sample_slop.html"), "--json"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(HERE), env=_subprocess_env(),
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue("ValueError" in r.stderr or "TypeError" in r.stderr, r.stderr)


if __name__ == "__main__":
    print_details()
    unittest.main(argv=[sys.argv[0]], verbosity=2)
