#!/usr/bin/python
"""AT-SPI actions restricted to the app that owns the focused Hyprland window."""
import json
import sys
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
Atspi.set_timeout(1000,1000)

def visible(node):
    states=node.get_state_set()
    return states.contains(Atspi.StateType.SHOWING) and states.contains(Atspi.StateType.VISIBLE)

def roots(apps, title):
    candidates=[]
    for app in apps:
        for index,node in enumerate(list(app)):
            try:
                if visible(node):candidates.append((node,[index]))
            except Exception:continue
    exact=[entry for entry in candidates if entry[0].get_name()==title]
    if len(exact)==1:return exact
    if len(candidates)==1:return candidates
    raise RuntimeError('Could not identify the active window in this app. Focus one window and try again.')

def discover(window_roots):
    controls=[];stack=list(window_roots);seen=0
    while stack and seen<3000:
        node,path=stack.pop();seen+=1
        try:
            states=node.get_state_set()
            if not (states.contains(Atspi.StateType.SHOWING) and states.contains(Atspi.StateType.VISIBLE)):continue
            name=node.get_name() or ''
            action=node.get_action_iface();edit=node.get_editable_text_iface()
            if name and (action or edit):
                controls.append({'node':node,'id':path,'name':name,'role':node.get_role_name(),
                    'editable':bool(edit),'disabled':not states.contains(Atspi.StateType.ENABLED)})
            children=list(node)
            stack.extend((child,path+[index]) for index,child in reversed(list(enumerate(children))))
        except Exception:continue
    return controls

def select(controls,request):
    expected=request.get('control')
    if expected:
        matches=[c for c in controls if c['id']==expected.get('id')]
        if len(matches)!=1 or any(matches[0].get(k)!=expected.get(k) for k in ('name','role')):
            raise RuntimeError('That control changed after observation. Inspect the current screen again.')
        return matches[0]
    target=request['target'].lower().strip()
    exact=[c for c in controls if c['name'].lower().strip()==target]
    matches=exact or [c for c in controls if target in c['name'].lower()]
    if len(matches)!=1:raise RuntimeError('More than one control matches; use its full label.' if matches else 'No visible control named '+request['target'])
    return matches[0]

def act(request):
    apps=[a for a in Atspi.get_desktop(0) if a.get_process_id()==request['pid']]
    if not apps:raise RuntimeError('This app does not expose accessible controls. Reopen it with accessibility enabled, or use a named app command.')
    controls=discover(roots(apps,request.get('window_title','')))
    if request['action']=='inspect':
        return {'controls':[{k:v for k,v in control.items() if k!='node'} for control in controls[:150]]}
    control=select(controls,request)
    node,name,role=control['node'],control['name'],control['role']
    if control['disabled']:raise RuntimeError('That control is disabled.')
    if role=='password text':raise RuntimeError('Type passwords directly in the app.')
    if request['action']=='fill':
        edit=node.get_editable_text_iface()
        if not edit or not edit.set_text_contents(request['text']):raise RuntimeError('The app rejected the text.')
        text=node.get_text_iface()
        if text and text.get_text(0,-1)!=request['text']:raise RuntimeError('The field did not retain the text.')
        return {'message':'Filled '+name,'verified':True,'evidence':'Field value read back exactly'}
    action=node.get_action_iface()
    if action and action.get_n_actions():
        for i in range(action.get_n_actions()):
            if action.get_action_name(i).lower() in ('click','press','activate','toggle'):
                if action.do_action(i):return {'message':'Activated '+name,'verified':False,'evidence':'Action dispatched; downstream effect has no verifier'}
    component=node.get_component_iface()
    if component and component.grab_focus():return {'message':'Focused '+name,'verified':True,'evidence':'Requested control owns focus'}
    raise RuntimeError('This control exposes no supported action.')
try:print(json.dumps(act(json.load(sys.stdin))))
except Exception as error:print(json.dumps({'error':str(error)}));sys.exit(1)
