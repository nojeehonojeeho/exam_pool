"""Use native nonbreaking spaces only within explicitly declared text phrases."""
import re


def protected_chunks(text, phrases):
    if not all(isinstance(p,str) and p and '\n' not in p for p in phrases):
        raise ValueError('invalid protected phrase')
    if not phrases:return [(False,text)] if text else []
    pattern=re.compile('|'.join(re.escape(p) for p in sorted(set(phrases),key=len,reverse=True)))
    result=[];end=0
    for match in pattern.finditer(text):
        if match.start()>end:result.append((False,text[end:match.start()]))
        parts=match.group().split(' ')
        for i,part in enumerate(parts):
            if i:result.append((True,' '))
            if part:result.append((False,part))
        end=match.end()
    if end<len(text):result.append((False,text[end:]))
    return result


def insert_protected_text(hwp,text,phrases=()):
    for nonbreaking,value in protected_chunks(text,phrases):
        if nonbreaking:
            if not hwp.InsertNonBreakingSpace():raise RuntimeError('NATIVE_NONBREAKING_SPACE_FAILED')
        else:hwp.insert_text(value)
