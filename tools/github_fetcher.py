import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BASE_URL = "https://api.github.com"
_AUTH = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
HEADERS = {**_AUTH, "Accept": "application/vnd.github.v3+json"}
MAX_FILE_SIZE = 200_000
MAX_FILES = 400

SKIP_DIRS = {
    ".git",
    ".github",
    ".next",
    ".nuxt",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
    "venv",
}

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".lock",
    ".min.js",
    ".map",
}


class GitHubRepositoryFetcher:
    """Fetches source files from public or private GitHub repositories using git clone."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = BASE_URL,
        max_files: int = MAX_FILES,
        max_file_size: int = MAX_FILE_SIZE,
        use_git_clone: bool = False,
    ) -> None:
        self.base_url = base_url
        self.max_files = max_files
        self.max_file_size = max_file_size
        _token = token or GITHUB_TOKEN
        _auth = {"Authorization": f"token {_token}"} if _token else {}
        self.headers = {**_auth, "Accept": "application/vnd.github.v3+json"}
        self.token = _token
        self.use_git_clone = use_git_clone
        self.temp_dir = None

    def parse_github_url(self, url: str) -> tuple[str, str]:
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("GitHub URL is required.")

        if "://" not in clean_url:
            clean_url = "https://" + clean_url

        parsed = urlparse(clean_url)
        host = parsed.netloc.lower()
        if host not in {"github.com", "www.github.com"}:
            raise ValueError("Please enter a github.com repository URL.")

        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 2:
            raise ValueError("GitHub URL must look like https://github.com/owner/repo.")

        owner = parts[0]
        repo = parts[1].replace(".git", "")
        return owner, repo

    def fetch_all_files(self, url: str) -> dict[str, str]:
        """Fetch files using git clone for better performance and private repo support."""
        owner, repo = self.parse_github_url(url)
        self._check_repo_accessible(owner, repo)

        if self.use_git_clone:
            return self._fetch_via_git_clone(url)
        return self._fetch_via_api(owner, repo)

    def _check_repo_accessible(self, owner: str, repo: str) -> None:
        """Pre-flight check: verify the repo exists and the token has access."""
        api_url = f"{self.base_url}/repos/{owner}/{repo}"
        try:
            response = requests.get(api_url, headers=self.headers, timeout=15)
        except requests.RequestException as error:
            raise RuntimeError(f"Could not reach GitHub API: {error}")

        if response.status_code == 200:
            return  # Accessible — proceed

        if response.status_code == 401:
            raise RuntimeError(
                "GitHub returned 401 Unauthorized. "
                "Your GITHUB_TOKEN is missing or invalid. "
                "Check the token in your .env file."
            )
        if response.status_code == 403:
            raise RuntimeError(
                "GitHub returned 403 Forbidden. "
                "Your GITHUB_TOKEN does not have permission to access this repository. "
                "Make sure the token has the 'repo' scope enabled in GitHub "
                "(Settings → Developer settings → Personal access tokens)."
            )
        if response.status_code == 404:
            raise RuntimeError(
                "Repository not found. "
                "If this is a private repository, make sure your GITHUB_TOKEN is set in .env "
                "and has the 'repo' scope. If it is public, double-check the URL."
            )
        raise RuntimeError(
            f"GitHub returned an unexpected status {response.status_code} "
            f"when checking repository access."
        )

    def _fetch_via_git_clone(self, url: str) -> dict[str, str]:
        """Clone repository locally and fetch files from disk, with fallback to API."""
        self.temp_dir = tempfile.mkdtemp(prefix="repo_audit_")
        
        try:
            # Build clone URL with token for private repos
            clone_url = self._build_clone_url(url)
            
            # Clone the repository with Git LFS disabled
            # This avoids timeout issues with large files
            env = os.environ.copy()
            env["GIT_LFS_SKIP_SMUDGE"] = "1"
            
            subprocess.run(
                ["git", "clone", "--depth", "1", "--single-branch", clone_url, self.temp_dir],
                check=True,
                capture_output=True,
                timeout=60,
                env=env,
            )
            
            # Fetch files from cloned directory
            file_contents = self._read_files_from_directory(self.temp_dir)
            return file_contents
            
        except subprocess.CalledProcessError as error:
            error_msg = error.stderr.decode() if error.stderr else str(error)
            print(f"Git clone failed: {error_msg}. Falling back to GitHub API...")
            
            # Fallback to API method
            try:
                owner, repo = self.parse_github_url(url)
                return self._fetch_via_api(owner, repo)
            except Exception as api_error:
                raise RuntimeError(f"Both git clone and API fetch failed. Git error: {error_msg}. API error: {str(api_error)}")
        
        except subprocess.TimeoutExpired:
            print("Git clone timed out. Falling back to GitHub API...")
            try:
                owner, repo = self.parse_github_url(url)
                return self._fetch_via_api(owner, repo)
            except Exception as api_error:
                raise RuntimeError(f"Git clone timed out and API fetch also failed: {str(api_error)}")
        
        except Exception as error:
            print(f"Unexpected error during git clone: {error}. Falling back to GitHub API...")
            try:
                owner, repo = self.parse_github_url(url)
                return self._fetch_via_api(owner, repo)
            except Exception as api_error:
                raise RuntimeError(f"Git clone failed and API fetch also failed: {str(api_error)}")

    def _build_clone_url(self, url: str) -> str:
        """Build clone URL with token for private repo authentication."""
        if self.token:
            # Insert token into HTTPS URL for authentication
            parsed = urlparse(url)
            if "://" in url:
                return url.replace("https://", f"https://{self.token}@").replace("http://", f"http://{self.token}@")
            return f"https://{self.token}@github.com/{url.replace('https://', '').replace('github.com/', '')}"
        return url

    def _read_files_from_directory(self, directory: str) -> dict[str, str]:
        """Read files from local directory."""
        file_contents: dict[str, str] = {}
        base_path = Path(directory)
        
        for file_path in base_path.rglob("*"):
            if len(file_contents) >= self.max_files:
                break
            
            if not file_path.is_file():
                continue
            
            # Skip files in excluded directories
            if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                continue
            
            # Skip binary files
            if file_path.suffix in SKIP_SUFFIXES:
                continue
            
            # Check file size
            try:
                if file_path.stat().st_size > self.max_file_size:
                    continue
            except OSError:
                continue
            
            # Read file content
            try:
                relative_path = str(file_path.relative_to(base_path))
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if content.strip():  # Only add non-empty files
                        file_contents[relative_path] = content
            except (UnicodeDecodeError, IOError):
                continue
        
        if not file_contents:
            raise RuntimeError("No readable source files were found in this repository.")
        
        return file_contents

    def _fetch_via_api(self, owner: str, repo: str) -> dict[str, str]:
        """Fallback to API-based fetching (for public repos only)."""
        file_contents: dict[str, str] = {}
        self._fetch_directory(owner, repo, "", file_contents)

        if not file_contents:
            raise RuntimeError("No readable source files were found in this repository.")

        return file_contents

    def _fetch_directory(
        self,
        owner: str,
        repo: str,
        path: str,
        file_contents: dict[str, str],
    ) -> None:
        if len(file_contents) >= self.max_files:
            return

        api_url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        response = requests.get(api_url, headers=self.headers, timeout=20)

        if response.status_code == 404:
            raise RuntimeError("Repository was not found, or it is not public.")
        if response.status_code == 403:
            raise RuntimeError("GitHub API rate limit reached. Add GITHUB_TOKEN to .env and try again.")
        if response.status_code != 200:
            raise RuntimeError(f"GitHub returned status {response.status_code}.")

        items = response.json()
        if not isinstance(items, list):
            return

        for item in items:
            if len(file_contents) >= self.max_files:
                return

            item_type = item.get("type")
            item_path = item.get("path", "")
            item_name = item.get("name", "")

            if item_type == "dir":
                if item_name.lower() not in SKIP_DIRS:
                    self._fetch_directory(owner, repo, item_path, file_contents)

            if item_type == "file":
                if self._should_skip_file(item_path, item.get("size", 0)):
                    continue
                content = self._fetch_file_content(item.get("download_url"))
                if content:
                    file_contents[item_path] = content

    def _should_skip_file(self, path: str, size: int) -> bool:
        lower_path = path.lower()
        if size > self.max_file_size:
            return True
        return any(lower_path.endswith(suffix) for suffix in SKIP_SUFFIXES)

    def _fetch_file_content(self, download_url: str | None) -> str | None:
        if not download_url:
            return None

        try:
            response = requests.get(download_url, headers=self.headers, timeout=20)
        except requests.RequestException:
            return None

        if response.status_code != 200:
            return None

        return response.text


def parse_github_url(url: str) -> tuple[str, str]:
    return GitHubRepositoryFetcher().parse_github_url(url)


def fetch_all_files(url: str) -> dict[str, str]:
    return GitHubRepositoryFetcher().fetch_all_files(url)


def _fetch_directory(owner: str, repo: str, path: str, file_contents: dict[str, str]) -> None:
    GitHubRepositoryFetcher()._fetch_directory(owner, repo, path, file_contents)


def _should_skip_file(path: str, size: int) -> bool:
    return GitHubRepositoryFetcher()._should_skip_file(path, size)


def _fetch_file_content(download_url: str | None) -> str | None:
    return GitHubRepositoryFetcher()._fetch_file_content(download_url)
