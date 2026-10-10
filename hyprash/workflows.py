"""Extract complete, destination-aware tasks before splitting ordinary clauses."""
import json
import re

def workflow(text):
    s=text.strip().strip('.!?').replace('’',"'")
    s=re.sub(r'^(?:please |can you |could you )','',s,flags=re.I)
    site=r'(google|youtube|spotify)(?:\s*dot\s*com|\.com)?'
    patterns=[rf'^(?:open|go to|visit) (?:www\.)?{site}(?: and(?: then)?| then) (search(?: for)?|play) (.+)$',
              rf'^{site} (search(?: for)?|play) (.+)$',
              rf'^(search(?: for)?|play) (.+?) on {site}$']
    for i,p in enumerate(patterns):
        m=re.fullmatch(p,s,re.I)
        if m:
            dest,verb,query=m.groups() if i<2 else (m[3],m[1],m[2])
            return 'web_task',json.dumps({'action':'play' if verb.lower()=='play' else 'search','site':dest.lower(),'query':query.strip()})
    m=re.fullmatch(r'(?:open|click)(?: on)? (?:the )?(first|second|third|fourth|fifth|\d+)(?: (?:link|result|video))(?: (?:that )?(?:showed up|popped up|on (?:the )?(?:google )?search))?',s,re.I)
    if m:
        index={'first':1,'second':2,'third':3,'fourth':4,'fifth':5}.get(m[1].lower(),int(m[1]) if m[1].isdigit() else 1)
        return 'web_task',json.dumps({'action':'result','index':index})
    m=re.fullmatch(r'(?:click|select|focus)(?: on)? (?:the )?(.+)',s,re.I)
    if m and not re.fullmatch(r'(?:address|url) bar',m[1],re.I):
        return 'ui_control',json.dumps({'action':'click','target':'Search' if m[1].lower()=='search bar' else m[1]})
    m=re.fullmatch(r'(?:type|enter) (.+?) (?:into (?:the )?|in the )(.+?)(?: field)?',s,re.I)
    if m:
        return 'ui_control',json.dumps({'action':'fill','target':m[2],'text':m[1]})
    return None
