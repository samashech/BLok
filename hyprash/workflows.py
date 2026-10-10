"""Extract complete, destination-aware tasks before splitting ordinary clauses."""
import json
import re

ORDINALS={'first':1,'second':2,'third':3,'fourth':4,'fifth':5}

def task_label(task):
    action=task['action']
    if action=='sequence':return ' then '.join(task_label(step) for step in task['steps'])
    if action=='new_tab':return 'Open a new browser tab'
    if action=='github_repo':return 'Open my GitHub repositories and open '+task['query']
    if action=='search':return 'Search '+task.get('site','the current site')+' for '+task['query']
    if action=='play':return 'Play '+('a song by ' if task.get('mode')=='artist' else '')+task['query']+' on '+task.get('site','Spotify')
    if action=='result':return ('Play video ' if task.get('play') else 'Open search result ')+str(task['index'])
    if action=='click':return 'Click '+task.get('target','')
    return 'Fill the '+task.get('target','')+' field with '+task.get('text','')

def workflow(text):
    s=text.strip().strip('.!?').replace('’',"'")
    s=re.sub(r'^(?:please |can you |could you )','',s,flags=re.I)
    m=re.fullmatch(r'(?:create|make)(?: a)?(?: new)? note (?:saying|that says|containing|with (?:the )?(?:text|content)) (.+?) in obsidian',s,re.I)
    if not m:
        m=re.fullmatch(r'(?:in obsidian[,.]? |(?:open )?obsidian and )(?:create|make)(?: a)?(?: new)? note (?:saying|that says|containing) (.+)',s,re.I)
    if m:return 'obsidian_note',json.dumps({'content':m[1]})
    if re.fullmatch(r'(?:(?:open|create)(?: up)? (?:a )?)?new (?:browser )?tab',s,re.I):
        return 'web_task',json.dumps({'action':'new_tab'})
    m=re.fullmatch(r'(?:open|go to) github(?:\.com)? and (?:then )?(?:go to|open) my repositories and (?:then )?(?:find|search for) (.+?) and (?:then )?open (?:it|the repository)',s,re.I)
    if m:return 'web_task',json.dumps({'action':'github_repo','query':m[1]})
    # Keep the search query and ordinal in one cancellable, ordered task.
    m=re.fullmatch(r'(.+?) (?:and(?: then)?|then) (?:play|open) (?:the )?(first|second|third|fourth|fifth|[1-9])(?: (?:video|result|one|link))?',s,re.I)
    if m:
        head=workflow(m[1])
        if head and head[0]=='web_task':
            task=json.loads(head[1])
            if task['action']=='search':
                index=ORDINALS.get(m[2].lower(),int(m[2]) if m[2].isdigit() else 1)
                return 'web_task',json.dumps({'action':'sequence','steps':[task,{'action':'result','index':index,'play':task.get('site')=='youtube'}]})
    site=r'(google|youtube|spotify)(?:\s*dot\s*com|\.com)?'
    patterns=[rf'^(?:open|go to|visit) (?:www\.)?{site}(?: and(?: then)?| then) (search(?: for)?|play) (.+)$',
              rf'^{site} (search(?: for)?|play) (.+)$',
              rf'^(search(?: for)?|play) (.+?) (?:on|in) {site}$']
    for i,p in enumerate(patterns):
        m=re.fullmatch(p,s,re.I)
        if m:
            dest,verb,query=m.groups() if i<2 else (m[3],m[1],m[2])
            task={'action':'play' if verb.lower()=='play' else 'search','site':dest.lower(),'query':query.strip()}
            if task['action']=='play' and task['site']=='spotify':
                artist=re.fullmatch(r'(?:a |any |some )?(.+?)(?: song| songs| music)',task['query'],re.I) or re.fullmatch(r'(?:a |any |some )?(?:song|music) by (.+)',task['query'],re.I)
                if artist:task.update(query=artist[1],mode='artist')
            return 'web_task',json.dumps(task)
    m=re.fullmatch(r'play (.+)',s,re.I)
    if m and not re.match(r'(?:the )?(?:first|second|third|fourth|fifth|[1-9])(?: |$)',m[1],re.I):
        return workflow('spotify play '+m[1])
    m=re.fullmatch(r'(?:open|click|play)(?: on)? (?:the )?(first|second|third|fourth|fifth|\d+)(?: (?:link|result|video))(?: (?:that )?(?:showed up|popped up|on (?:the )?(?:google )?search))?',s,re.I)
    if m:
        index={'first':1,'second':2,'third':3,'fourth':4,'fifth':5}.get(m[1].lower(),int(m[1]) if m[1].isdigit() else 1)
        return 'web_task',json.dumps({'action':'result','index':index,**({'play':True} if s.lower().startswith('play ') else {})})
    m=re.fullmatch(r'(?:click|select|focus)(?: on)? (?:the )?(.+)',s,re.I)
    if m and not re.fullmatch(r'(?:address|url) bar',m[1],re.I):
        return 'ui_control',json.dumps({'action':'click','target':'Search','role':'field'} if m[1].lower()=='search bar' else {'action':'click','target':m[1]})
    m=re.fullmatch(r'(?:type|enter) (.+?) (?:into (?:the )?|in the )(.+?)(?: field)?',s,re.I)
    if m:
        return 'ui_control',json.dumps({'action':'fill','target':m[2],'text':m[1]})
    return None
