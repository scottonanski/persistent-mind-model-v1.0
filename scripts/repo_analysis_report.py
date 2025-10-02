import ast
import os
from collections import defaultdict

ROOT_DIR = "pmm"
TARGET_FILE = os.path.join(ROOT_DIR, "runtime", "loop.py")
OUTPUT_FILE = "analysis_report.md"


def get_defs(path):
    """Extract top-level class and function names from a Python file."""
    with open(path, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=path)
        except SyntaxError:
            return []
    names = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names.append(f"def {node.name}")
        elif isinstance(node, ast.ClassDef):
            names.append(f"class {node.name}")
    return names


def build_index(root):
    index = defaultdict(list)
    for dirpath, _, files in os.walk(root):
        for fname in files:
            if fname.endswith(".py"):
                fpath = os.path.join(dirpath, fname)
                index[fpath] = get_defs(fpath)
    return index


def main():
    index = build_index(ROOT_DIR)
    loop_defs = index.get(TARGET_FILE, [])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(f"# Analysis of {TARGET_FILE}\n\n")

        out.write(f"## Top-level definitions in loop.py ({len(loop_defs)})\n\n")
        for name in loop_defs:
            out.write(f"- {name}\n")

        out.write("\n## Overlaps with other files\n\n")
        for fpath, defs in index.items():
            if fpath == TARGET_FILE:
                continue
            overlap = set(loop_defs) & set(defs)
            if overlap:
                out.write(f"### {fpath}\n\n")
                out.write("| Overlapping Definitions |\n")
                out.write("|--------------------------|\n")
                for item in sorted(overlap):
                    out.write(f"| {item} |\n")
                out.write("\n")

    print(f"Report written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
