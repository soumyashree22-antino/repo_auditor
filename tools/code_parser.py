import re


CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".swift",
    ".kt",
    ".scala",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
}

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".swift": "Swift",
    ".kt": "Kotlin",
}

KEY_FILE_NAMES = {
    "readme.md",
    "readme.txt",
    "readme",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "pom.xml",
    "build.gradle",
    "cargo.toml",
    "go.mod",
    "composer.json",
    "gemfile",
    "dockerfile",
    "docker-compose.yml",
    "main.py",
    "app.py",
    "index.js",
    "server.js",
    "main.go",
    "main.rs",
}


class RepositoryCodeAnalyzer:
    """Reusable static analysis helper for repository files."""

    def __init__(self, file_contents: dict[str, str]):
        self.file_contents = file_contents

    def guess_primary_language(self) -> str:
        counts: dict[str, int] = {}
        for path, content in self.file_contents.items():
            language = LANGUAGE_BY_EXTENSION.get(get_extension(path))
            if language:
                counts[language] = counts.get(language, 0) + len(content.splitlines())
        if not counts:
            return ""
        return max(counts, key=counts.get)

    def chunk_files(self, chunk_size: int = 200) -> list[str]:
        chunks = []
        for filepath, content in self.file_contents.items():
            filename = filepath.rsplit("/", 1)[-1].lower()
            if not is_code_file(filepath) and filename not in KEY_FILE_NAMES:
                continue
            lines = content.splitlines()
            for start in range(0, len(lines), chunk_size):
                block = lines[start : start + chunk_size]
                header = f"--- FILE: {filepath} (lines {start + 1}-{start + len(block)}) ---"
                chunks.append(header + "\n" + "\n".join(block))
        return chunks

    def build_limited_context(self, chunk_size: int = 160, max_chars: int = 80000) -> str:
        selected_chunks = []
        total_chars = 0

        for chunk in self.chunk_files(chunk_size=chunk_size):
            if total_chars + len(chunk) > max_chars:
                break
            selected_chunks.append(chunk)
            total_chars += len(chunk)

        return "\n\n".join(selected_chunks)

    def get_key_files(self) -> dict[str, str]:
        key_files = {}
        for path, content in self.file_contents.items():
            filename = path.rsplit("/", 1)[-1].lower()
            if filename in KEY_FILE_NAMES:
                key_files[path] = content
        return key_files

    def get_flat_file_tree(self) -> str:
        return "\n".join(sorted(self.file_contents.keys()))

    def get_project_tree(self, max_lines: int = 300) -> str:
        paths = sorted(self.file_contents.keys())
        tree: dict[str, dict] = {}
        for path in paths:
            cursor = tree
            for part in path.split("/"):
                cursor = cursor.setdefault(part, {})

        lines = ["."]
        self._render_tree(tree, "", lines, max_lines)
        if len(lines) > max_lines:
            hidden_count = max(0, len(paths) - max_lines)
            lines = lines[:max_lines]
            lines.append(f"... {hidden_count} more path(s) omitted")
        return "\n".join(lines)

    def get_component_map(self, max_items: int = 80) -> list[str]:
        components = []
        for path, content in sorted(self.file_contents.items()):
            for symbol in self._extract_symbols(path, content):
                components.append(symbol)
                if len(components) >= max_items:
                    return components
        return components

    def _render_tree(
        self,
        node: dict[str, dict],
        prefix: str,
        lines: list[str],
        max_lines: int,
    ) -> None:
        if len(lines) >= max_lines:
            return

        items = sorted(node.items(), key=lambda item: (bool(item[1]), item[0].lower()))
        for index, (name, child) in enumerate(items):
            if len(lines) >= max_lines:
                return
            is_last = index == len(items) - 1
            connector = "`-- " if is_last else "|-- "
            suffix = "/" if child else ""
            lines.append(f"{prefix}{connector}{name}{suffix}")
            if child:
                extension = "    " if is_last else "|   "
                self._render_tree(child, prefix + extension, lines, max_lines)

    def _extract_symbols(self, path: str, content: str) -> list[str]:
        extension = get_extension(path)
        if extension == ".py":
            return self._extract_python_symbols(path, content)
        if extension in {".js", ".jsx", ".ts", ".tsx"}:
            return self._extract_javascript_symbols(path, content)
        return []

    def _extract_python_symbols(self, path: str, content: str) -> list[str]:
        symbols = []
        pattern = re.compile(r"^\s*(class|def|async\s+def)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
        for match in pattern.finditer(content):
            kind = "async function" if match.group(1).startswith("async") else match.group(1)
            name = match.group(2)
            line_number = content[: match.start()].count("\n") + 1
            symbols.append(f"{path}:{line_number} - {kind} `{name}`")
        return symbols

    def _extract_javascript_symbols(self, path: str, content: str) -> list[str]:
        symbols = []
        patterns = [
            (r"\bclass\s+([A-Za-z_$][A-Za-z0-9_$]*)", "class"),
            (r"\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)", "function"),
            (r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\(", "function"),
            (r"\bexport\s+(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)", "function"),
        ]
        for raw_pattern, kind in patterns:
            for match in re.finditer(raw_pattern, content):
                name = match.group(1)
                line_number = content[: match.start()].count("\n") + 1
                symbols.append(f"{path}:{line_number} - {kind} `{name}`")
        return symbols


def get_extension(filepath: str) -> str:
    name = filepath.rsplit("/", 1)[-1].lower()
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1]


def is_code_file(filepath: str) -> bool:
    return get_extension(filepath) in CODE_EXTENSIONS


def guess_primary_language(file_contents: dict[str, str]) -> str:
    return RepositoryCodeAnalyzer(file_contents).guess_primary_language()


def chunk_files(file_contents: dict[str, str], chunk_size: int = 200) -> list[str]:
    return RepositoryCodeAnalyzer(file_contents).chunk_files(chunk_size=chunk_size)


def build_limited_context(
    file_contents: dict[str, str],
    chunk_size: int = 160,
    max_chars: int = 80000,
) -> str:
    return RepositoryCodeAnalyzer(file_contents).build_limited_context(
        chunk_size=chunk_size,
        max_chars=max_chars,
    )


def get_key_files(file_contents: dict[str, str]) -> dict[str, str]:
    return RepositoryCodeAnalyzer(file_contents).get_key_files()


def get_file_tree(file_contents: dict[str, str]) -> str:
    return RepositoryCodeAnalyzer(file_contents).get_flat_file_tree()


def get_project_tree(file_contents: dict[str, str], max_lines: int = 300) -> str:
    return RepositoryCodeAnalyzer(file_contents).get_project_tree(max_lines=max_lines)


def get_component_map(file_contents: dict[str, str], max_items: int = 80) -> list[str]:
    return RepositoryCodeAnalyzer(file_contents).get_component_map(max_items=max_items)
