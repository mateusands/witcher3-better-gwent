"""Execute a restricted pure AS3 subset as JS for numeric fixture parity.

This is an explicitly scoped source adapter, NOT Flash execution. FFDec compiles
AS3 separately. Native scheduling/type coercions need in-game acceptance.
"""
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TYPE=r'(?:Vector\.\<[^>]+\>|[A-Za-z_]\w*)'


def close_brace(text,start):
    depth=1;i=start
    while depth:
        if text[i]=='{':depth+=1
        elif text[i]=='}':depth-=1
        i+=1
    return i


def strip_types(text,params=False):
    if params:return re.sub(r'(\b\w+):'+TYPE,r'\1',text)
    text = re.sub(r'(\bcatch\(\w+):'+TYPE,r'\1',text)
    text = text.replace('error is GwaiV8Unsupported', 'error instanceof GwaiV8Unsupported').replace('error is GwaiV8Budget','error instanceof GwaiV8Budget')
    return re.sub(r'(\bvar \w+):'+TYPE,r'\1',text)


def qualify(text,members,locals_,class_name):
    tokens=r'"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|//[^\n]*|\b[A-Za-z_]\w*\b'
    # Keep offsets while excluding comments from the preceding-token check.
    code=re.sub(tokens,lambda m:' '*len(m[0]) if m[0].startswith('//') else m[0],text)
    def replace(match):
        word=match[0]
        # The class name itself (constructor) is a class reference, not an instance member.
        if word not in members or word in locals_ or word==class_name:return word
        before=code[:match.start()].rstrip();after=code[match.end():].lstrip()
        # A colon after a ternary operand is not an object-key delimiter.
        object_key = after.startswith(':') and before.endswith(('{', ','))
        if before.endswith('.') or object_key:return word
        return (class_name if members[word] else 'this')+'.'+word
    return re.sub(tokens,replace,text)


def javascript(source):
    outputs=[]
    for match in re.finditer(r'internal class (\w+)(?: extends (\w+))?\s*\{',source):
        name,base=match.groups();body=source[match.end():close_brace(source,match.end())-1]
        fields=list(re.finditer(r'(?:public|private) (static )?(?:var|const) (\w+):'+TYPE+r'\s*=\s*([^;]+);',body))
        methods=list(re.finditer(r'(?:public|private) (static )?function (\w+)\(([^)]*)\)(?:\s*:'+TYPE+r')?\s*\{',body))
        members={f[2]:bool(f[1]) for f in fields};members.update({m[2]:bool(m[1]) for m in methods})
        parts=[]
        for f in fields:
            parts.append(('static ' if f[1] else '')+f[2]+' = '+f[3]+';')
        for method in methods:
            flag,method_name,params=method.groups();text=body[method.end():close_brace(body,method.end())-1]
            params=strip_types(params,True)
            local=set(re.findall(r'\bvar (\w+)',text))|set(re.findall(r'(?:^|,)\s*(\w+)',params))
            text=strip_types(text);text=qualify(text,members,local,name)
            # Preserve AS3's numeric sort flag in the explicit JS subset.
            text=text.replace('.sort(Array.NUMERIC)', '.sort((a,b) => a-b)')
            text=text.replace('value is Array', 'Array.isArray(value)').replace('value is Boolean', '(typeof value === \"boolean\")').replace('value is Number', '(typeof value === \"number\")').replace('value is String', '(typeof value === \"string\")')
            parts.append(('static ' if flag else '')+('constructor' if method_name==name else method_name)+'('+params+') {\n'+text+'\n}')
        outputs.append('class '+name+(' extends '+base if base else '')+' {\n'+'\n'.join(parts)+'\n}')
    return '\n'.join(outputs)


def core_javascript():
    files=['GwaiV8Const','GwaiV8Position','GwaiV8Capture','GwaiV8Reserve','GwaiV8Sequence','GwaiV8Random','GwaiV8Hash','GwaiV8Belief','GwaiV8Response','GwaiV8Policy','GwaiV8Context','GwaiV8Execution','GwaiV8SequenceTask','GwaiV8Runner']
    return 'function int(v) { return v|0; } function uint(v) { return v>>>0; }\n'+javascript('\n'.join((ROOT/f'mod/v8/as3/{name}.as').read_text() for name in files))
