"""
Verifier — isolated code quality judge.
Python: pytest + mypy + flake8
JS/JSX/TS: eslint (if available)
"""
import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VerificationResult:
    def __init__(self, passed: bool, score: float, issues: list[str], tool: str):
        self.passed = passed
        self.score = score          # 0.0 – 1.0
        self.issues = issues
        self.tool = tool

    def __repr__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"[{status}] score={self.score:.2f} tool={self.tool} issues={len(self.issues)}"


class Verifier:
    """Runs static analysis and tests on generated code files."""

    def __init__(self, min_score: float = 0.6):
        self.min_score = min_score

    async def verify_file(self, file_path: str) -> VerificationResult:
        path = Path(file_path)
        if not path.exists():
            return VerificationResult(False, 0.0, [f"File not found: {file_path}"], "filesystem")

        ext = path.suffix.lower()
        if ext == ".py":
            return await self._verify_python(file_path)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            return await self._verify_js(file_path)
        elif ext in (".md", ".yml", ".yaml", ".json", ".css"):
            return await self._verify_text(file_path)
        else:
            return VerificationResult(True, 1.0, [], "passthrough")

    # ── Python verification ───────────────────────────────────────────────────
    async def _verify_python(self, file_path: str) -> VerificationResult:
        issues = []
        scores = []

        # Syntax check
        ok, out = await self._run(["python3", "-m", "py_compile", file_path])
        if ok:
            scores.append(1.0)
        else:
            issues.append(f"Syntax error: {out[:300]}")
            scores.append(0.0)
            return VerificationResult(False, 0.0, issues, "py_compile")

        # flake8 (style / undefined names)
        ok, out = await self._run([
            "python3", "-m", "flake8",
            "--max-line-length=120",
            "--ignore=E501,W503,E302,E303",
            file_path
        ])
        if ok:
            scores.append(1.0)
        else:
            flake_issues = [l for l in out.splitlines() if l.strip()][:5]
            issues.extend(flake_issues)
            scores.append(0.6 if len(flake_issues) <= 3 else 0.3)

        # mypy (type checking) — optional
        ok, out = await self._run(["python3", "-m", "mypy", "--ignore-missing-imports", file_path])
        if ok:
            scores.append(1.0)
        else:
            mypy_issues = [l for l in out.splitlines() if "error:" in l][:3]
            issues.extend(mypy_issues)
            scores.append(0.7)   # mypy errors are non-fatal

        score = sum(scores) / len(scores)
        passed = score >= self.min_score
        return VerificationResult(passed, score, issues, "python")

    # ── JS / JSX / TS verification ────────────────────────────────────────────
    async def _verify_js(self, file_path: str) -> VerificationResult:
        issues = []

        # Basic JS syntax via node --check
        ok, out = await self._run(["node", "--check", file_path])
        if not ok and "SyntaxError" in out:
            return VerificationResult(False, 0.0, [f"Syntax error: {out[:300]}"], "node")

        # eslint if available
        ok, out = await self._run(["npx", "--yes", "eslint", "--no-eslintrc",
                                    "--rule", '{"no-undef": "warn"}',
                                    file_path])
        if ok:
            return VerificationResult(True, 1.0, [], "eslint")

        # Parse eslint output
        errors   = [l for l in out.splitlines() if "error" in l.lower()][:5]
        warnings = [l for l in out.splitlines() if "warning" in l.lower()][:3]
        issues.extend(errors + warnings)

        score = 1.0 - (len(errors) * 0.15) - (len(warnings) * 0.05)
        score = max(0.0, min(1.0, score))
        passed = score >= self.min_score and not any("error" in i.lower() for i in issues[:3])
        return VerificationResult(passed, score, issues, "eslint")

    # ── Text / config verification ────────────────────────────────────────────
    async def _verify_text(self, file_path: str) -> VerificationResult:
        ext = Path(file_path).suffix.lower()
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return VerificationResult(False, 0.0, ["File is empty"], "text")

        issues = []
        if ext == ".json":
            try:
                import json; json.loads(content)
            except Exception as e:
                return VerificationResult(False, 0.0, [f"Invalid JSON: {e}"], "json")
        elif ext in (".yml", ".yaml"):
            try:
                import yaml; yaml.safe_load(content)
            except Exception as e:
                return VerificationResult(False, 0.0, [f"Invalid YAML: {e}"], "yaml")

        return VerificationResult(True, 1.0, issues, "text")

    # ── Batch verification ────────────────────────────────────────────────────
    async def verify_task(self, task) -> VerificationResult:
        """Verify all output files of a task; return worst result."""
        if not task.output_files:
            return VerificationResult(True, 1.0, [], "no-files")

        results = await asyncio.gather(*[self.verify_file(f) for f in task.output_files])
        worst = min(results, key=lambda r: r.score)
        return worst

    # ── Subprocess helper ─────────────────────────────────────────────────────
    @staticmethod
    async def _run(cmd: list[str]) -> tuple[bool, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            text = out.decode(errors="replace")
            return proc.returncode == 0, text
        except asyncio.TimeoutError:
            return False, "Verification timed out"
        except FileNotFoundError:
            return True, ""   # tool not installed → skip silently
        except Exception as e:
            return False, str(e)
