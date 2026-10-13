import os
import sys
import shutil
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Common Windows compiler and JDK installation paths
EXTRA_COMPILER_PATHS = [
    Path(r"C:\TDM-GCC-32\bin"),
    Path(r"C:\TDM-GCC-64\bin"),
    Path(r"C:\MinGW\bin"),
    Path(r"C:\Users\manoj\jdk-17\bin"),
    Path(r"C:\Program Files\Java\jdk-17\bin"),
    Path(r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot\bin"),
]
if os.environ.get("JAVA_HOME"):
    EXTRA_COMPILER_PATHS.insert(0, Path(os.environ["JAVA_HOME"]) / "bin")

def find_tool(name: str) -> Optional[str]:
    """Locate tool via PATH or known Windows fallback paths."""
    found = shutil.which(name)
    if found:
        return found
    exe_name = f"{name}.exe" if not name.endswith(".exe") else name
    for folder in EXTRA_COMPILER_PATHS:
        candidate = folder / exe_name
        if candidate.exists():
            return str(candidate)
    return None

class LanguageSpec:
    """Specification for a programming language supported by CodeMind execution engine."""

    def __init__(
        self,
        id: str,
        name: str,
        extension: str,
        needs_compilation: bool,
        default_filename: str,
        compiler_name: Optional[str] = None,
        runtime_name: Optional[str] = None
    ):
        self.id = id
        self.name = name
        self.extension = extension
        self.needs_compilation = needs_compilation
        self.default_filename = default_filename
        self.compiler_name = compiler_name
        self.runtime_name = runtime_name

    def get_source_filename(self, source_code: str) -> str:
        if self.id == "java":
            # Extract public class name if specified
            match = re.search(r'\bpublic\s+class\s+([A-Za-z_][A-Za-z0-9_]*)', source_code)
            if match:
                return f"{match.group(1)}.java"
            match_any = re.search(r'\bclass\s+([A-Za-z_][A-Za-z0-9_]*)', source_code)
            if match_any:
                return f"{match_any.group(1)}.java"
            return "Solution.java"
        return self.default_filename

    def is_available(self) -> Tuple[bool, Optional[str]]:
        """Check if required compiler and runtime are installed on the host."""
        if self.id == "python":
            return True, f"Python {sys.version.split()[0]} ({sys.executable})"

        if self.id == "c":
            path = find_tool(self.compiler_name or "gcc")
            if path:
                return True, f"GCC ({path})"
            clang_path = find_tool("clang")
            if clang_path:
                return True, f"Clang ({clang_path})"
            return False, "C compiler (gcc/clang) not found on system"

        if self.id == "cpp":
            path = find_tool(self.compiler_name or "g++")
            if path:
                return True, f"G++ ({path})"
            clang_path = find_tool("clang++")
            if clang_path:
                return True, f"Clang++ ({clang_path})"
            return False, "C++ compiler (g++/clang++) not found on system"

        if self.id == "java":
            javac_path = find_tool(self.compiler_name or "javac")
            java_path = find_tool(self.runtime_name or "java")
            if javac_path and java_path:
                return True, f"Java JDK ({javac_path})"
            if not javac_path and not java_path:
                return False, "Java compiler (javac) and runtime (java) not found on system"
            if not javac_path:
                return False, "Java compiler (javac) not found on system"
            return False, "Java runtime (java) not found on system"

        return False, f"Unsupported language: {self.id}"

    def get_compile_command(self, workdir: Path, source_file: str) -> Optional[List[str]]:
        """Return compilation command list if needed."""
        if not self.needs_compilation:
            return None

        src_path = str(workdir / source_file)

        bin_name = "solution.exe" if os.name == "nt" else "solution"
        if self.id == "c":
            compiler = find_tool(self.compiler_name or "gcc") or "gcc"
            out_path = str(workdir / bin_name)
            return [compiler, src_path, "-O2", "-o", out_path]

        if self.id == "cpp":
            compiler = find_tool(self.compiler_name or "g++") or "g++"
            out_path = str(workdir / bin_name)
            return [compiler, src_path, "-O2", "-std=c++17", "-o", out_path]

        if self.id == "java":
            javac = find_tool(self.compiler_name or "javac") or "javac"
            return [javac, "-d", str(workdir), src_path]

        return None

    def get_run_command(self, workdir: Path, source_file: str) -> List[str]:
        """Return execution command list."""
        if self.id == "python":
            return [sys.executable, str(workdir / source_file)]

        if self.id in ("c", "cpp"):
            bin_name = "solution.exe" if os.name == "nt" else "solution"
            return [str(workdir / bin_name)]

        if self.id == "java":
            class_name = Path(source_file).stem
            java = find_tool(self.runtime_name or "java") or "java"
            return [java, "-cp", str(workdir), class_name]

        raise ValueError(f"Unknown run command for {self.id}")


SUPPORTED_LANGUAGES: Dict[str, LanguageSpec] = {
    "python": LanguageSpec(
        id="python",
        name="Python",
        extension=".py",
        needs_compilation=False,
        default_filename="solution.py",
        runtime_name="python"
    ),
    "c": LanguageSpec(
        id="c",
        name="C",
        extension=".c",
        needs_compilation=True,
        default_filename="solution.c",
        compiler_name="gcc"
    ),
    "cpp": LanguageSpec(
        id="cpp",
        name="C++",
        extension=".cpp",
        needs_compilation=True,
        default_filename="solution.cpp",
        compiler_name="g++"
    ),
    "java": LanguageSpec(
        id="java",
        name="Java",
        extension=".java",
        needs_compilation=True,
        default_filename="Solution.java",
        compiler_name="javac",
        runtime_name="java"
    ),
}

# Aliases mapping
LANGUAGE_ALIASES: Dict[str, str] = {
    "py": "python",
    "python3": "python",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "g++": "cpp",
    "gcc": "c",
    "java": "java",
}

def resolve_language(lang: Optional[str]) -> Optional[LanguageSpec]:
    """Normalize language string and return LanguageSpec or None."""
    if not lang:
        return None
    key = str(lang).strip().lower()
    canonical_id = LANGUAGE_ALIASES.get(key, key)
    return SUPPORTED_LANGUAGES.get(canonical_id)

def list_supported_languages() -> List[Dict[str, Any]]:
    """Return status of all supported languages."""
    results = []
    for spec in SUPPORTED_LANGUAGES.values():
        available, info = spec.is_available()
        results.append({
            "id": spec.id,
            "name": spec.name,
            "available": available,
            "info": info
        })
    return results

