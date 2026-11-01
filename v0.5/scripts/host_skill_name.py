"""Read host skill names conservatively without silently ignoring YAML syntax."""
import json
import re


def scalar(value):
    value = value.strip()
    if value.startswith('"'):
        result, end = json.JSONDecoder().raw_decode(value)
        suffix = value[end:].strip()
        if not isinstance(result, str) or (suffix and not suffix.startswith('#')):
            raise ValueError('unsupported quoted scalar')
        return result
    if value.startswith("'"):
        match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", value)
        if not match:
            raise ValueError('unsupported quoted scalar')
        return match[1].replace("''", "'")
    return re.split(r'\s+#', value, maxsplit=1)[0].strip()


def declared_name(text):
    if not text.startswith('---\n'):
        return None
    if '\n---' not in text[4:]:
        raise ValueError('unterminated skill frontmatter')
    lines = text[4:].split('\n---', 1)[0].splitlines()
    meaningful = [line for line in lines if line.strip() and not line.lstrip().startswith('#')]
    if meaningful and meaningful[0].startswith((' ', '\t')):
        raise ValueError('indented frontmatter requires explicit name reconciliation')
    values = []
    for index, line in enumerate(lines):
        if not line.strip() or line.startswith((' ', '\t', '#')):
            continue
        if ':' not in line:
            raise ValueError('unsupported skill frontmatter mapping')
        raw_key, value = line.split(':', 1)
        key = scalar(raw_key)
        if not re.fullmatch('[a-zA-Z][a-zA-Z0-9_-]*', key):
            raise ValueError('unsupported skill frontmatter key')
        if key != 'name':
            continue
        value = value.strip()
        if re.fullmatch(r'[>|][+-]?(?:\s+#.*)?', value):
            body = []
            for continuation in lines[index + 1:]:
                if continuation and not continuation.startswith(' '):
                    break
                if continuation.strip():
                    body.append(continuation.strip())
            # Host names are single tokens. Complex/multiline values cannot be
            # classified safely and block activation until reconciled.
            if len(body) != 1:
                raise ValueError('unsupported multiline skill name')
            value = body[0]
        else:
            value = scalar(value)
        if not re.fullmatch('[a-z][a-z0-9-]*', value):
            raise ValueError('unsupported skill name declaration')
        values.append(value)
    if len(values) > 1:
        raise ValueError('ambiguous skill name declaration')
    return values[0] if values else None
