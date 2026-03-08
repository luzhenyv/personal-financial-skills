import re
import sys
from pathlib import Path


def escape_currency_dollars(text: str) -> str:
    """
    Escape dollar signs used as currency so Typora doesn't parse them as
    inline LaTeX formulas.

    Rules:
    - Skip already-escaped dollar signs: \$
    - Skip LaTeX inline math: $...$ or $$...$$
    - Escape dollar signs followed by digits or amounts like $300, $1.5B
    """
    result = []
    i = 0
    n = len(text)

    while i < n:
        # Already escaped — keep as-is
        if text[i] == '\\' and i + 1 < n and text[i + 1] == '$':
            result.append('\\$')
            i += 2
            continue

        if text[i] == '$':
            # Check for display math: $$...$$
            if i + 1 < n and text[i + 1] == '$':
                # Find closing $$
                end = text.find('$$', i + 2)
                if end != -1:
                    result.append(text[i:end + 2])
                    i = end + 2
                    continue

            # Check for inline math: $...$
            # Heuristic: if the char after $ is NOT a digit, treat as LaTeX
            if i + 1 < n and not re.match(r'[\d.,]', text[i + 1]):
                # Find closing $
                end = text.find('$', i + 1)
                if end != -1:
                    result.append(text[i:end + 1])
                    i = end + 1
                    continue

            # Otherwise, it's a currency dollar sign — escape it
            result.append('\\$')
            i += 1
            continue

        result.append(text[i])
        i += 1

    return ''.join(result)


def clean_markdown_file(input_path: str, output_path: str | None = None) -> None:
    path = Path(input_path)
    if not path.exists():
        print(f"Error: File '{input_path}' not found.")
        sys.exit(1)

    original = path.read_text(encoding='utf-8')
    cleaned = escape_currency_dollars(original)

    out_path = Path(output_path) if output_path else path
    out_path.write_text(cleaned, encoding='utf-8')

    changes = original.count('$') - cleaned.count('$') + cleaned.count('\\$') - original.count('\\$')
    print(f"✅ Done. {changes} dollar sign(s) escaped → '{out_path}'")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python clean_markdown.py <input.md> [output.md]")
        print("       If output.md is omitted, the file is modified in place.")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    clean_markdown_file(input_file, output_file)