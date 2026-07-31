import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / 'app' / 'templates'

DEFAULT_RE = re.compile(r"\|default:(\"[^\"]*\"|'[^']*'|\d+)")
FLOATFORMAT_RE = re.compile(r"\|floatformat:(\d+)")
ADD_RE = re.compile(r'\|add:"-0"')


def convert(text):
    text = DEFAULT_RE.sub(lambda m: f'|default({m.group(1)})', text)
    text = FLOATFORMAT_RE.sub(lambda m: f'|floatformat({m.group(1)})', text)
    text = ADD_RE.sub('', text)
    return text


def main():
    count = 0
    for path in TEMPLATES_DIR.rglob('*.html'):
        original = path.read_text(encoding='utf-8')
        converted = convert(original)
        if converted != original:
            path.write_text(converted, encoding='utf-8')
            count += 1
    print(f'Archivos corregidos: {count}')


if __name__ == '__main__':
    main()
