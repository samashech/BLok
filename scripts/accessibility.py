#!/usr/bin/python
"""AT-SPI actions restricted to the app that owns the focused Hyprland window."""
import json
import sys
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
Atspi.set_timeout(1000,1000)

def act(request):
    apps=[a for a in Atspi.get_desktop(0) if a.get_process_id()==request['pid']]
    if not apps:raise RuntimeError('This app does not expose accessible controls. Reopen it with accessibility enabled, or use a named app command.')
    controls=[];stack=list(apps);seen=0
    while stack and seen<3000:
        node=stack.pop();seen+=1
        try:
            states=node.get_state_set()
            if states.contains(Atspi.StateType.SHOWING) and states.contains(Atspi.StateType.VISIBLE):
                name=node.get_name() or ''
                if name:controls.append((node,name,node.get_role_name()))
            stack.extend(reversed(list(node)))
        except Exception:continue
    if request['action']=='inspect':return {'controls':[{'name':n,'role':r} for _,n,r in controls][:150]}
    target=request['target'].lower().strip()
    candidates=[(e,n,r) for e,n,r in controls if n.lower().strip()==target and (e.get_action_iface() or e.get_editable_text_iface())]
    if not candidates:candidates=[(e,n,r) for e,n,r in controls if target in n.lower() and (e.get_action_iface() or e.get_editable_text_iface())]
    if len(candidates)!=1:raise RuntimeError('More than one control matches; use its full label.' if candidates else 'No visible control named '+request['target'])
    node,name,role=candidates[0]
    if role=='password text':raise RuntimeError('Type passwords directly in the app.')
    if request['action']=='fill':
        edit=node.get_editable_text_iface()
        if not edit or not edit.set_text_contents(request['text']):raise RuntimeError('The app rejected the text.')
        text=node.get_text_iface()
        if text and text.get_text(0,-1)!=request['text']:raise RuntimeError('The field did not retain the text.')
        return {'message':'Filled '+name}
    action=node.get_action_iface()
    if action and action.get_n_actions():
        for i in range(action.get_n_actions()):
            if action.get_action_name(i).lower() in ('click','press','activate','toggle'):
                if action.do_action(i):return {'message':'Activated '+name}
    component=node.get_component_iface()
    if component and component.grab_focus():return {'message':'Focused '+name}
    raise RuntimeError('This control exposes no supported action.')
try:print(json.dumps(act(json.load(sys.stdin))))
except Exception as error:print(json.dumps({'error':str(error)}));sys.exit(1)
