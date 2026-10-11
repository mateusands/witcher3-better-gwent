"""Diagnostic-only build step: tag errors with the V8 function chain they pass through.

Each function body is wrapped in try/catch that appends "<Class.method>" to the error message
and rethrows the same error object (type unchanged, so GwaiV8Unsupported/GwaiV8Budget logic is
unaffected). The game's Scaleform reports only "Error #1006", so this chain locates the call.
Never applied to the V8 sources themselves; release builds should omit it.
"""
import re


def close_brace(code, start):
    """Index just after the brace that closes the one opened right before `start`."""
    depth, i, n = 1, start, len(code)
    while i < n:
        c = code[i]
        if c in '"\'':
            q = c; i += 1
            while i < n and code[i] != q:
                i += 2 if code[i] == '\\' else 1
        elif code.startswith('//', i):
            i = code.index('\n', i)
        elif code.startswith('/*', i):
            i = code.index('*/', i) + 1
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError('unbalanced braces')


HEADER = re.compile(r'function\s+(?:get\s+|set\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*[\w.*<>]+)?\s*\{')


def instrument(code, cls):
    out, pos, count = [], 0, 0
    for m in HEADER.finditer(code):
        if m.start() < pos:
            continue
        body_start = m.end()
        end = close_brace(code, body_start)
        body = code[body_start:end - 1]
        tag = '<%s.%s>' % (cls, m.group(1))
        wrapped = ('\n try {' + body + '\n }\n catch(gwaiTraceError:Error)\n {\n'
                   '  if(gwaiTraceError.message.length < 400) gwaiTraceError.message += "%s";\n'
                   '  throw gwaiTraceError;\n }\n' % tag)
        out.append(code[pos:body_start]); out.append(wrapped); out.append('}')
        pos = end; count += 1
    out.append(code[pos:])
    return ''.join(out), count
