#!/usr/bin/env python3
"""Validate a Markdown document tree. File fragments/anchors are not checked."""

import argparse
from bisect import bisect_right
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


def blank(text):
    """Mask content without changing line numbers or character offsets."""
    return "".join("\n" if char == "\n" else " " for char in text)


def without_code(text):
    lines = text.splitlines(keepends=True)
    fence = None
    indented = False
    previous_blank = True
    for index, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) +
                            "{" + str(len(fence)) + r",}\s*", line):
                fence = None
            lines[index] = blank(line)
        elif marker:
            fence = marker.group(1)
            lines[index] = blank(line)
        else:
            has_indent = line.startswith("    ") or line.startswith("\t")
            # Nested list items are navigation, not indented code blocks.
            list_item = re.match(r"^\s*(?:[-+*]|\d+[.)])\s", line)
            if (indented or previous_blank) and has_indent and not list_item:
                indented = True
                lines[index] = blank(line)
            elif line.strip():
                indented = False
        previous_blank = not line.strip()
    result = "".join(lines)
    return re.sub(r"(?<!`)(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)",
                  lambda match: blank(match.group()), result)


def escaped(text, index):
    count = 0
    while index > 0 and text[index - 1] == "\\":
        count += 1
        index -= 1
    return count % 2 == 1


def closing_bracket(text, start):
    depth = 1
    for index in range(start + 1, len(text)):
        if escaped(text, index):
            continue
        if text[index] == "[":
            depth += 1
        elif text[index] == "]":
            depth -= 1
            if depth == 0:
                return index
    return None


def destination(text, start):
    """Read an angle-bracket or balanced, unquoted Markdown destination."""
    if start < len(text) and text[start] == "<":
        end = start + 1
        while end < len(text) and text[end] != "\n":
            if text[end] == ">" and not escaped(text, end):
                return text[start + 1:end], end + 1
            end += 1
        return None
    end, depth = start, 0
    while end < len(text):
        char = text[end]
        if not escaped(text, end):
            if char.isspace() or (char == ")" and depth == 0):
                break
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
        end += 1
    return (text[start:end], end) if end > start and depth == 0 else None


def normalize(label):
    return " ".join(label.split()).casefold()


def markdown_links(text):
    """Yield (destination, source line) for inline and resolved reference links."""
    text = without_code(text)
    definitions = {}
    chars = list(text)
    for match in re.finditer(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(.*)$", text, re.M):
        parsed = destination(match.group(2), 0)
        if parsed:
            definitions.setdefault(normalize(match.group(1)), parsed[0])
            chars[match.start():match.end()] = blank(match.group())
    text = "".join(chars)
    newlines = [index for index, char in enumerate(text) if char == "\n"]
    index = 0
    while index < len(text):
        start = text.find("[", index)
        if start < 0:
            break
        index = start + 1
        if escaped(text, start) or (start > 0 and text[start - 1] == "!"):
            continue
        end = closing_bracket(text, start)
        if end is None:
            continue
        target = None
        after = end + 1
        if text[after:after + 1] == "(":
            target_start = after + 1
            while target_start < len(text) and text[target_start].isspace():
                target_start += 1
            parsed = destination(text, target_start)
            if parsed:
                candidate, target_end = parsed
                suffix = re.match(r"\s*(?:\"[^\"\n]*\"|'[^'\n]*'|\([^\n]*?\))?\s*\)",
                                  text[target_end:])
                if suffix:
                    target = candidate
                    index = target_end + suffix.end()
        else:
            reference_start = after
            while reference_start < len(text) and text[reference_start].isspace():
                reference_start += 1
            label = text[start + 1:end]
            if text[reference_start:reference_start + 1] == "[":
                reference_end = closing_bracket(text, reference_start)
                if reference_end is not None:
                    label = text[reference_start + 1:reference_end] or label
                    index = reference_end + 1
            else:
                index = after
            target = definitions.get(normalize(label))
        if target is not None:
            yield re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])", r"\1", target), bisect_right(newlines, start) + 1


def inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate(root):
    root = root.resolve()
    entry = root / "README.md"
    errors = []
    if not entry.is_file():
        return [f"{entry}: missing root README.md"], 0, 0
    pages = sorted(path for path in root.rglob("*")
                   if path.is_file() and path.suffix.casefold() == ".md")
    graph = {path.resolve(): set() for path in pages}
    link_count = 0
    for page in pages:
        location = str(page.relative_to(root))
        try:
            content = page.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"{location}: cannot read Markdown: {error}")
            continue
        for target, line in markdown_links(content):
            if target.startswith("//"):
                continue
            windows_absolute = bool(re.match(r"^[A-Za-z]:[\\/]", target))
            try:
                parsed = urlsplit(target)
            except ValueError:
                errors.append(f"{location}:{line}: invalid link destination: {target!r}")
                continue
            if parsed.scheme and parsed.scheme != "file" and not windows_absolute:
                continue
            path_text = unquote(parsed.path)
            if Path(path_text).suffix.casefold() != ".md":
                continue
            link_count += 1
            target_path = Path(path_text)
            resolved = (page.parent / target_path).resolve()
            in_tree = inside(resolved, root)
            prefix = f"{location}:{line}"
            if windows_absolute or (target_path.is_absolute() and in_tree):
                errors.append(f"{prefix}: use a relative link for a document in this tree: {target!r}")
            if not resolved.is_file():
                errors.append(f"{prefix}: missing Markdown target {target!r} (resolved to {resolved})")
            elif in_tree and resolved in graph:
                graph[page.resolve()].add(resolved)
    reached, pending = set(), [entry.resolve()]
    while pending:
        page = pending.pop()
        if page not in reached:
            reached.add(page)
            pending.extend(graph.get(page, ()))
    for page in pages:
        if page.resolve() not in reached:
            errors.append(f"{page.relative_to(root)}: unreachable from README.md")
    return errors, len(pages), link_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="document directory containing README.md")
    args = parser.parse_args()
    errors, page_count, link_count = validate(args.root)
    print("File fragments are ignored; anchors are not checked.")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"FAIL: {len(errors)} error(s), {page_count} Markdown page(s), {link_count} Markdown link(s).")
        return 1
    print(f"OK: {page_count} Markdown page(s), {link_count} Markdown link(s); all pages reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
