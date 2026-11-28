#!/usr/bin/env python3
"""对比 unslop-audit 与 impeccable detect 的替代可行性。

只做观察，不改变现有测试判定，也不把 impeccable 加入项目依赖。
详细命令、stdout/stderr 与原始 JSON 记入 .agents/tmp/impeccable-comparison/，
控制台只输出对照摘要和 WARNING 以上日志。

运行：
    uv run python tests/compare_impeccable.py
    uv run python tests/compare_impeccable.py --json
    IMPPECCABLE_BIN=/path/to/impeccable uv run python tests/compare_impeccable.py
    IMPECCABLE_CWD=/path/outside/repo uv run python tests/compare_impeccable.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
AUDIT_SCRIPT = ROOT / "ai_ui_audit.py"
SLOP = HERE / "sample_slop.html"
CLEAN = HERE / "sample_clean.html"
UNIT_DIR = HERE / "unittests"
OUT_DIR = ROOT / ".agents" / "tmp" / "impeccable-comparison"
LOG_PATH = OUT_DIR / "compare_impeccable.log"

logger = logging.getLogger("compare-impeccable")


def inside_git_repo(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def resolve_impeccable_cwd() -> Path:
    override = os.environ.get("IMPECCABLE_CWD")
    candidate = Path(override).expanduser() if override else Path(tempfile.gettempdir())
    candidate = candidate.resolve()
    fallback = Path(tempfile.gettempdir()).resolve()
    if not candidate.is_dir() or inside_git_repo(candidate):
        logger.warning(
            "IMPECCABLE_CWD 不可用或仍在 git 仓库内: %s，改用 %s", candidate, fallback
        )
        candidate = fallback
    return candidate


def configure_logging() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    file_handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter("WARNING: %(message)s"))
    logger.addHandler(console_handler)

    logger.info("==== compare_impeccable 开始 ====")


def first_value(mapping: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def scalar_value(value):
    if isinstance(value, dict):
        return first_value(value, ("id", "name", "rule", "code"))
    if isinstance(value, (str, int, float, bool)):
        return value
    return None


def to_int(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def normalize_path(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\\", "/").lower()


def run_external(argv: list[str], label: str, *, cwd: Path = ROOT) -> dict:
    logger.info("[%s] cwd=%s cmd=%s", label, cwd, subprocess.list2cmdline(argv))
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        # Windows 上 pnpm/npm 生成的 .cmd 垫片有时需要显式经 cmd.exe 启动。
        if os.name == "nt" and argv[0].lower().endswith((".cmd", ".bat")):
            wrapped = ["cmd.exe", "/c", subprocess.list2cmdline(argv)]
            logger.info("[%s] retry via cmd.exe=%s", label, subprocess.list2cmdline(wrapped))
            try:
                result = subprocess.run(
                    wrapped,
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
            except OSError as wrapped_exc:
                message = f"{label} 启动失败: {wrapped_exc}"
                logger.error(message)
                logger.warning(message)
                return {
                    "ok": False,
                    "error": str(wrapped_exc),
                    "returncode": None,
                    "stdout": "",
                    "stderr": "",
                    "argv": argv,
                    "cwd": str(cwd),
                }
        else:
            message = f"{label} 启动失败: {exc}"
            logger.error(message)
            logger.warning(message)
            return {
                "ok": False,
                "error": str(exc),
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "argv": argv,
                "cwd": str(cwd),
            }

    logger.info("[%s] exit=%s", label, result.returncode)
    logger.info("[%s] stdout=%s", label, result.stdout)
    logger.info("[%s] stderr=%s", label, result.stderr)
    return {
        "ok": True,
        "error": "",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "argv": argv,
        "cwd": str(cwd),
    }


def parse_json(run: dict, label: str):
    if not run["ok"]:
        return None
    try:
        return json.loads(run["stdout"])
    except json.JSONDecodeError as exc:
        message = f"{label} 的 stdout 不是合法 JSON: {exc}"
        logger.error(message)
        logger.warning(message)
        return None


def pick_records(payload):
    """从 JSON 中挑出主 finding 与 advisory finding 列表。"""
    if isinstance(payload, list):
        return payload, []

    if isinstance(payload, dict):
        primary_keys = ("findings", "issues", "results", "violations")
        advisory_keys = ("advisories", "advisoryFindings", "warnings")
        primary = next(
            (payload[key] for key in primary_keys if isinstance(payload.get(key), list)),
            None,
        )
        advisory = next(
            (payload[key] for key in advisory_keys if isinstance(payload.get(key), list)),
            None,
        )
        if primary is not None or advisory is not None:
            return primary or [], advisory or []
        for value in payload.values():
            nested_primary, nested_advisory = pick_records(value)
            if nested_primary or nested_advisory:
                return nested_primary, nested_advisory
    return [], []


def normalize_record(record) -> dict:
    if not isinstance(record, dict):
        return {"rule": "", "severity": "", "line": None, "path": "", "raw": record}

    location = first_value(
        record, ("location", "range", "position", "loc", "sourceLocation")
    )
    location = location if isinstance(location, dict) else {}
    start = first_value(record, ("start", "begin"))
    start = start if isinstance(start, dict) else {}

    rule = scalar_value(
        first_value(
            record,
            (
                "antipattern",
                "antipattern_id",
                "ruleId",
                "rule_id",
                "rule",
                "id",
                "name",
                "pattern",
                "code",
            ),
        )
    )
    severity = scalar_value(
        first_value(record, ("severity", "level", "impact", "category"))
    )
    line = to_int(
        first_value(record, ("line", "lineNumber", "startLine", "start_line", "row"))
    )
    if line is None:
        line = to_int(
            first_value(location, ("line", "lineNumber", "startLine", "start_line"))
        )
    if line is None and start:
        line = to_int(first_value(start, ("line", "lineNumber", "startLine")))

    return {
        "rule": str(rule) if rule is not None else "",
        "severity": str(severity) if severity is not None else "",
        "line": line,
        "path": normalize_path(
            first_value(record, ("file", "path", "filePath", "filename", "file_name"))
        ),
        "raw": record,
    }


def normalize_records(records) -> list[dict]:
    return [normalize_record(record) for record in records]


def run_unslop(target: Path, name: str, *, fail_on: bool = False) -> dict:
    csv_path = OUT_DIR / "csv" / f"unslop-{name}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        str(AUDIT_SCRIPT),
        str(target),
        "--json",
        "--csv",
        str(csv_path),
    ]
    if fail_on:
        argv.extend(("--fail-on", "high"))
    return run_external(argv, f"unslop:{name}")


def run_impeccable(target: Path, name: str, impeccable_bin: str, cwd: Path) -> dict:
    argv = [impeccable_bin, "detect", "--json", "--no-config", str(target)]
    return run_external(argv, f"impeccable:{name}", cwd=cwd)


def scan_one(target: Path, name: str, impeccable_bin: str, cwd: Path) -> dict:
    unslop_run = run_unslop(target, name, fail_on=True)
    imp_run = run_impeccable(target, name, impeccable_bin, cwd)

    unslop_payload = parse_json(unslop_run, f"unslop:{name}")
    imp_payload = parse_json(imp_run, f"impeccable:{name}")

    unslop_primary, _ = pick_records(unslop_payload)
    imp_primary, imp_advisory = pick_records(imp_payload)

    unslop_findings = normalize_records(unslop_primary)
    imp_findings = normalize_records(imp_primary)
    imp_advice = normalize_records(imp_advisory)

    if imp_payload is not None:
        log_path = OUT_DIR / f"impeccable-{name}.json"
        log_path.write_text(
            json.dumps(imp_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("[impeccable:%s] raw json=%s", name, log_path)

    return {
        "name": name,
        "target": str(target),
        "unslop": {
            "available": unslop_run["ok"] and unslop_payload is not None,
            "exit_code": unslop_run["returncode"],
            "findings": len(unslop_findings),
            "lines": sorted(
                {item["line"] for item in unslop_findings if item["line"] is not None}
            ),
            "records": unslop_findings,
        },
        "impeccable": {
            "available": imp_run["ok"] and imp_payload is not None,
            "exit_code": imp_run["returncode"],
            "primary": len(imp_findings),
            "advisory": len(imp_advice),
            "lines": sorted(
                {item["line"] for item in imp_findings if item["line"] is not None}
            ),
            "records": imp_findings,
            "advisory_records": imp_advice,
        },
    }


def fixture_cases() -> list[tuple[str, Path, Path | None]]:
    cases = []
    if not UNIT_DIR.is_dir():
        return cases
    for directory in sorted(item for item in UNIT_DIR.iterdir() if item.is_dir()):
        html = directory / "case.html"
        tsx = directory / "case.tsx"
        if html.exists() or tsx.exists():
            cases.append(
                (directory.name, html if html.exists() else None, tsx if tsx.exists() else None)
            )
    return cases


def scan_fixtures(impeccable_bin: str, cwd: Path) -> dict:
    csv_path = OUT_DIR / "csv" / "unslop-fixtures.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    unslop_run = run_external(
        [
            sys.executable,
            str(AUDIT_SCRIPT),
            str(UNIT_DIR),
            "--json",
            "--csv",
            str(csv_path),
        ],
        "unslop:fixtures",
    )
    imp_run = run_external(
        [impeccable_bin, "detect", "--json", "--no-config", str(UNIT_DIR)],
        "impeccable:fixtures",
        cwd=cwd,
    )

    unslop_payload = parse_json(unslop_run, "unslop:fixtures")
    imp_payload = parse_json(imp_run, "impeccable:fixtures")

    unslop_records, _ = pick_records(unslop_payload)
    imp_records, imp_advisory = pick_records(imp_payload)
    unslop_findings = normalize_records(unslop_records)
    imp_findings = normalize_records(imp_records)
    imp_advice = normalize_records(imp_advisory)

    if imp_payload is not None:
        log_path = OUT_DIR / "impeccable-fixtures.json"
        log_path.write_text(
            json.dumps(imp_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("[impeccable:fixtures] raw json=%s", log_path)

    result = {
        "available": {
            "unslop": unslop_run["ok"] and unslop_payload is not None,
            "impeccable": imp_run["ok"] and imp_payload is not None,
        },
        "counts": {
            "unslop": len(unslop_findings),
            "impeccable_primary": len(imp_findings),
            "impeccable_advisory": len(imp_advice),
        },
        "html": {"total": 0, "unslop": [], "impeccable": [], "both": []},
        "tsx": {"total": 0, "unslop": [], "impeccable": [], "both": []},
    }

    for rule_name, html, tsx in fixture_cases():
        for kind, path in (("html", html), ("tsx", tsx)):
            if path is None:
                continue
            suffix = f"/{rule_name}/{path.name}"
            unslop_hit = any(item["path"].endswith(suffix) for item in unslop_findings)
            imp_hit = any(item["path"].endswith(suffix) for item in imp_findings)
            result[kind]["total"] += 1
            if unslop_hit:
                result[kind]["unslop"].append(rule_name)
            if imp_hit:
                result[kind]["impeccable"].append(rule_name)
            if unslop_hit and imp_hit:
                result[kind]["both"].append(rule_name)

    for kind in ("html", "tsx"):
        result[kind]["unslop_only"] = sorted(
            set(result[kind]["unslop"]) - set(result[kind]["impeccable"])
        )
        result[kind]["impeccable_only"] = sorted(
            set(result[kind]["impeccable"]) - set(result[kind]["unslop"])
        )
    return result


def build_report(impeccable_bin: str, cwd: Path) -> dict:
    slop = scan_one(SLOP, "sample_slop", impeccable_bin, cwd)
    clean = scan_one(CLEAN, "sample_clean", impeccable_bin, cwd)
    fixtures = scan_fixtures(impeccable_bin, cwd)

    json_ok = slop["unslop"]["available"] and slop["impeccable"]["available"]
    clean_blockers = clean["impeccable"]["primary"] + clean["impeccable"]["advisory"]
    clean_rules = sorted(
        {
            item["rule"]
            for group in (
                clean["impeccable"]["records"],
                clean["impeccable"]["advisory_records"],
            )
            for item in group
            if item["rule"]
        }
    )
    slop_lines = {
        line for line in slop["unslop"]["lines"] if line is not None and line > 0
    }
    imp_lines = {
        line for line in slop["impeccable"]["lines"] if line is not None and line > 0
    }
    overlap_lines = slop_lines & imp_lines

    html_total = fixtures["html"]["total"] or 1
    tsx_total = fixtures["tsx"]["total"] or 1
    html_ratio = len(fixtures["html"]["both"]) / html_total
    tsx_ratio = len(fixtures["tsx"]["both"]) / tsx_total

    if not json_ok:
        verdict = "无法判断：至少一个工具没有产出可解析的 JSON"
    elif clean_blockers == 0 and html_ratio >= 0.9 and tsx_ratio >= 0.9:
        verdict = "基本可替代：本地样本覆盖和干净页门禁均达到当前粗粒度预筛要求"
    elif clean_blockers == 0 and (html_ratio >= 0.6 or tsx_ratio >= 0.6):
        verdict = "可部分替代：建议保留现有脚本作为规则级 CI 门禁"
    else:
        verdict = "暂不能替代：存在明显漏检或干净页新增阻塞项"

    return {
        "impeccable_bin": impeccable_bin,
        "impeccable_cwd": str(cwd),
        "samples": {"slop": slop, "clean": clean},
        "fixtures": fixtures,
        "summary": {
            "json_parseable": json_ok,
            "clean_blocked_findings": clean_blockers,
            "clean_blocker_rules": clean_rules,
            "sample_slop_line_overlap": len(overlap_lines),
            "sample_slop_unslop_only_lines": len(slop_lines - imp_lines),
            "sample_slop_impeccable_only_lines": len(imp_lines - slop_lines),
            "html_fixture_overlap_ratio": round(html_ratio, 3),
            "tsx_fixture_overlap_ratio": round(tsx_ratio, 3),
            "impeccable_dirty_exit_code": slop["impeccable"]["exit_code"],
            "impeccable_clean_exit_code": clean["impeccable"]["exit_code"],
            "verdict": verdict,
        },
        "log": str(LOG_PATH),
    }


def print_text_report(report: dict) -> None:
    summary = report["summary"]
    slop = report["samples"]["slop"]
    clean = report["samples"]["clean"]
    fixtures = report["fixtures"]

    print("impeccable 替代可行性对照")
    print("=" * 64)
    print(f"impeccable 命令: {report['impeccable_bin']}")
    print(f"impeccable cwd : {report['impeccable_cwd']}")
    print(f"详细日志: {report['log']}")
    print()

    print("[整页样本]")
    print(
        f"  sample_slop.html : unslop {slop['unslop']['findings']:>3} finding "
        f"(exit {slop['unslop']['exit_code']}) | "
        f"impeccable {slop['impeccable']['primary']:>3} primary / "
        f"{slop['impeccable']['advisory']:>3} advisory "
        f"(exit {slop['impeccable']['exit_code']})"
    )
    print(
        f"  sample_clean.html: unslop {clean['unslop']['findings']:>3} finding "
        f"(exit {clean['unslop']['exit_code']}) | "
        f"impeccable {clean['impeccable']['primary']:>3} primary / "
        f"{clean['impeccable']['advisory']:>3} advisory "
        f"(exit {clean['impeccable']['exit_code']})"
    )
    print(
        f"  干净页按当前基线新增的阻塞项: {summary['clean_blocked_findings']} "
        f"({', '.join(summary['clean_blocker_rules']) or '无'})"
    )
    print()

    print("[行级重叠 sample_slop.html，排除 line=0]")
    print(
        f"  两工具都报的行: {summary['sample_slop_line_overlap']} | "
        f"仅 unslop: {summary['sample_slop_unslop_only_lines']} | "
        f"仅 impeccable: {summary['sample_slop_impeccable_only_lines']}"
    )
    print()

    print("[规则级 fixture 覆盖]")
    for kind, label in (("html", "HTML"), ("tsx", "TSX")):
        bucket = fixtures[kind]
        print(
            f"  {label}: 重叠 {len(bucket['both'])}/{bucket['total']} | "
            f"unslop {len(bucket['unslop'])} | impeccable {len(bucket['impeccable'])}"
        )
        if bucket["impeccable_only"]:
            print(f"    仅 impeccable 命中: {', '.join(bucket['impeccable_only'])}")
        print(f"    仅 unslop 命中: {', '.join(bucket['unslop_only']) or '无'}")
    print()

    print("[结构化输出与门禁]")
    print(f"  两工具 JSON 可解析: {'是' if summary['json_parseable'] else '否'}")
    print(
        f"  impeccable 干净页 exit: {summary['impeccable_clean_exit_code']} | "
        f"脏页 exit: {summary['impeccable_dirty_exit_code']} "
        "(0=仅 advisory 或无 finding，2=有 primary finding)"
    )
    print()
    print(f"结论: {summary['verdict']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--impeccable",
        default=os.environ.get("IMPECCABLE_BIN", "impeccable"),
        help="impeccable 可执行文件路径（默认 PATH 中的 impeccable）",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON 报告")
    args = parser.parse_args()

    configure_logging()
    impeccable_bin = shutil.which(args.impeccable) or args.impeccable
    impeccable_cwd = resolve_impeccable_cwd()
    logger.info("impeccable cwd=%s", impeccable_cwd)
    report = build_report(impeccable_bin, impeccable_cwd)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
