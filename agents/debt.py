import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.report import DebtIssue
from tools.code_parser import build_limited_context, is_code_file
from tools.json_utils import extract_json_list
from tools.llm_client import call_llm

load_dotenv()


class DebtAuditor:
    """Finds maintainability and architecture issues in repository code."""

    def run(self, state: dict) -> dict:
        file_contents = state["file_contents"]
        heuristic_results = self.heuristic_scan(file_contents)
        llm_results = self.llm_scan(file_contents)
        all_findings = self.deduplicate_findings(heuristic_results + llm_results)
        return {**state, "debt_findings": all_findings}

    def heuristic_scan(self, file_contents: dict[str, str]) -> list[dict]:
        return heuristic_scan(file_contents)

    def llm_scan(self, file_contents: dict[str, str]) -> list[dict]:
        return llm_scan(file_contents)

    def deduplicate_findings(self, findings: list[dict]) -> list[dict]:
        return deduplicate_findings(findings)


def run_debt(state: dict) -> dict:
    return DebtAuditor().run(state)


def heuristic_scan(file_contents: dict[str, str]) -> list[dict]:
    findings = []

    for filepath, content in file_contents.items():
        if not is_code_file(filepath):
            continue

        lines = content.splitlines()
        if len(lines) > 800:
            findings.append(
                {
                    "file": filepath,
                    "line": 1,
                    "issue": "Large source file",
                    "type": "architecture",
                    "snippet": f"{filepath} has {len(lines)} lines.",
                    "suggestion": "Split this file into smaller modules with one clear responsibility each.",
                }
            )

        findings.extend(find_todos(filepath, lines))
        findings.extend(find_weak_error_handling(filepath, lines))
        findings.extend(find_long_python_functions(filepath, lines))

    findings.extend(find_duplicate_lines(file_contents))
    return validate_debt_issues(findings)


def find_todos(filepath: str, lines: list[str]) -> list[dict]:
    findings = []
    for line_number, line in enumerate(lines, start=1):
        if re.search(r"\b(TODO|FIXME|HACK)\b", line, flags=re.IGNORECASE):
            findings.append(
                {
                    "file": filepath,
                    "line": line_number,
                    "issue": "Unresolved maintenance note",
                    "type": "dead_code",
                    "snippet": line.strip()[:300],
                    "suggestion": "Convert this note into a tracked issue or complete the missing work.",
                }
            )
    return findings


def find_weak_error_handling(filepath: str, lines: list[str]) -> list[dict]:
    findings = []
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped in {"except:", "except Exception:", "catch (e) {", "catch(e) {"}:
            findings.append(
                {
                    "file": filepath,
                    "line": line_number,
                    "issue": "Broad error handling",
                    "type": "error_handling",
                    "snippet": stripped,
                    "suggestion": "Catch a specific error type and handle it with a clear recovery path.",
                }
            )
    return findings


def find_long_python_functions(filepath: str, lines: list[str]) -> list[dict]:
    if not filepath.endswith(".py"):
        return []

    findings = []
    current_name = ""
    current_start = 0

    for line_number, line in enumerate(lines, start=1):
        if re.match(r"^\s*def\s+\w+\(", line):
            if current_name and line_number - current_start > 60:
                findings.append(build_long_function_issue(filepath, current_start, current_name))
            current_name = line.strip()
            current_start = line_number

    if current_name and len(lines) - current_start > 60:
        findings.append(build_long_function_issue(filepath, current_start, current_name))

    return findings


def build_long_function_issue(filepath: str, line_number: int, function_line: str) -> dict:
    return {
        "file": filepath,
        "line": line_number,
        "issue": "Long function",
        "type": "complexity",
        "snippet": function_line,
        "suggestion": "Break this function into smaller helper functions that each do one job.",
    }


def find_duplicate_lines(file_contents: dict[str, str]) -> list[dict]:
    line_map: dict[str, tuple[str, int]] = {}
    findings = []

    for filepath, content in file_contents.items():
        if not is_code_file(filepath):
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            normalized = line.strip()
            if len(normalized) < 45 or normalized.startswith(("#", "//", "*")):
                continue

            if normalized in line_map:
                first_file, first_line = line_map[normalized]
                findings.append(
                    {
                        "file": filepath,
                        "line": line_number,
                        "issue": "Duplicated logic",
                        "type": "duplication",
                        "snippet": normalized[:300],
                        "suggestion": f"Extract the duplicated line shared with {first_file}:{first_line} into a reusable helper.",
                    }
                )
                if len(findings) >= 10:
                    return findings
            else:
                line_map[normalized] = (filepath, line_number)

    return findings


def llm_scan(file_contents: dict[str, str]) -> list[dict]:
    code_context = build_limited_context(file_contents, chunk_size=80, max_chars=40000)
    if not code_context:
        return []

    try:
        raw_text = call_llm(
            system_prompt=load_prompt("debt_prompt.txt"),
            user_message=code_context,
            max_tokens=600,
        )
        if not raw_text:
            return []
        parsed = parse_json_list(raw_text)
        return validate_debt_issues(parsed)
    except Exception as error:
        print(f"Debt LLM scan failed: {error}")
        return []


def validate_debt_issues(items: list[dict]) -> list[dict]:
    valid_items = []
    for item in items:
        try:
            valid_items.append(DebtIssue.model_validate(item).model_dump())
        except ValidationError:
            continue
    return valid_items


def deduplicate_findings(findings: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for finding in findings:
        key = (finding.get("file"), finding.get("line"), finding.get("issue"))
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def load_prompt(name: str) -> str:
    with open(f"prompts/{name}", "r", encoding="utf-8") as file:
        return file.read()


def parse_json_list(raw_text: str) -> list[dict]:
    try:
        return extract_json_list(raw_text)
    except ValueError:
        return []


if __name__ == "__main__":
    sample_state = {
        "file_contents": {
            "app.py": "# TODO: remove this later\ntry:\n    risky()\nexcept Exception:\n    pass\n",
        }
    }
    print(run_debt(sample_state)["debt_findings"])
