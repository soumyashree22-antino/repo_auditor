import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.report import SecurityIssue
from tools.code_parser import build_limited_context
from tools.json_utils import extract_json_list
from tools.llm_client import call_llm

load_dotenv()


REGEX_PATTERNS = [
    (
        r"(api[_-]?key|secret|token)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']",
        "Hardcoded Secret",
        "CRITICAL",
        "A secret-like value is stored directly in source code.",
    ),
    (
        r"(password|passwd|pwd)\s*[:=]\s*[\"'][^\"']{8,}[\"']",
        "Hardcoded Password",
        "CRITICAL",
        "A password is stored directly in source code.",
    ),
    (
        r"ghp_[A-Za-z0-9]{36}",
        "GitHub Token",
        "CRITICAL",
        "A GitHub token appears to be exposed in source code.",
    ),
    (
        r"sk-ant-[A-Za-z0-9_\-]{20,}",
        "Anthropic API Key",
        "CRITICAL",
        "An Anthropic API key appears to be exposed in source code.",
    ),
    (
        r"sk-[A-Za-z0-9]{32,}",
        "API Key",
        "CRITICAL",
        "An API key appears to be exposed in source code.",
    ),
    (
        r"BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY",
        "Private Key",
        "CRITICAL",
        "A private key appears to be stored in the repository.",
    ),
    (
        r"\beval\s*\(",
        "Use of eval",
        "HIGH",
        "eval can execute attacker-controlled code if input reaches it.",
    ),
    (
        r"\bexec\s*\(",
        "Use of exec",
        "HIGH",
        "exec can execute attacker-controlled code if input reaches it.",
    ),
    (
        r"pickle\.loads\s*\(",
        "Insecure Deserialization",
        "HIGH",
        "pickle.loads can execute code when it reads untrusted data.",
    ),
    (
        r"shell\s*=\s*True",
        "Shell Command Injection Risk",
        "HIGH",
        "shell=True can allow command injection if any argument is user-controlled.",
    ),
    (
        r"debug\s*=\s*True",
        "Debug Mode Enabled",
        "MEDIUM",
        "Debug mode can expose internal information in production.",
    ),
]


class SecurityAuditor:
    """Finds security issues with deterministic regex rules plus optional LLM review."""

    def run(self, state: dict) -> dict:
        file_contents = state["file_contents"]
        regex_results = self.regex_scan(file_contents)
        llm_results = self.llm_scan(file_contents)
        all_findings = self.deduplicate_findings(regex_results + llm_results)
        return {**state, "security_findings": all_findings}

    def regex_scan(self, file_contents: dict[str, str]) -> list[dict]:
        return regex_scan(file_contents)

    def llm_scan(self, file_contents: dict[str, str]) -> list[dict]:
        return llm_scan(file_contents)

    def deduplicate_findings(self, findings: list[dict]) -> list[dict]:
        return deduplicate_findings(findings)


def run_security(state: dict) -> dict:
    return SecurityAuditor().run(state)


def regex_scan(file_contents: dict[str, str]) -> list[dict]:
    findings = []
    for filepath, content in file_contents.items():
        for line_number, line in enumerate(content.splitlines(), start=1):
            for pattern, issue_name, severity, explanation in REGEX_PATTERNS:
                if re.search(pattern, line, flags=re.IGNORECASE):
                    findings.append(
                        {
                            "file": filepath,
                            "line": line_number,
                            "issue": issue_name,
                            "severity": severity,
                            "snippet": line.strip()[:300],
                            "explanation": explanation,
                        }
                    )
    return validate_security_issues(findings)


def llm_scan(file_contents: dict[str, str]) -> list[dict]:
    code_context = build_limited_context(file_contents, chunk_size=80, max_chars=40000)
    if not code_context:
        return []

    try:
        raw_text = call_llm(
            system_prompt=load_prompt("security_prompt.txt"),
            user_message=code_context,
            max_tokens=600,
        )
        if not raw_text:
            return []
        parsed = parse_json_list(raw_text)
        return validate_security_issues(parsed)
    except Exception as error:
        print(f"Security LLM scan failed: {error}")
        return []


def validate_security_issues(items: list[dict]) -> list[dict]:
    valid_items = []
    for item in items:
        try:
            valid_items.append(SecurityIssue.model_validate(item).model_dump())
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
            "settings.py": "API_KEY = 'abc123abc123abc123abc123'\ndebug=True\n",
        }
    }
    print(run_security(sample_state)["security_findings"])
