import json
import unittest
from unittest.mock import Mock, patch

from hyprash.backend import Backend
from hyprash.commands import Action
from hyprash import desktop


class DesktopDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.owner = {'address':'0x1','pid':42,'title':'Notes','class':'notes'}
        self.observation = {'owner':self.owner,'controls':[
            {'id':[0,1],'name':'Search','role':'text','editable':True,'disabled':False},
            {'id':[0,2],'name':'Save','role':'push button','editable':False,'disabled':False},
            {'id':[0,3],'name':'Archive','role':'push button','editable':False,'disabled':True},
        ]}

    def test_discovery_selects_one_semantic_control(self):
        self.assertEqual(desktop.select_control(self.observation,{'action':'fill','target':'Search','role':'field'})['id'],[0,1])
        self.assertEqual(desktop.select_control(self.observation,{'action':'click','target':'Save'})['id'],[0,2])
        with self.assertRaisesRegex(RuntimeError,'disabled'):
            desktop.select_control(self.observation,{'action':'click','target':'Archive'})

    def test_owner_change_rejects_before_accessibility_action(self):
        changed={**self.owner,'address':'0x2'}
        with patch.object(desktop,'active_owner',return_value=changed),patch.object(desktop,'_accessibility') as accessibility:
            with self.assertRaisesRegex(RuntimeError,'active window changed'):
                desktop.control({'action':'click','target':'Save'},owner=self.owner)
        accessibility.assert_not_called()

    def test_backend_observes_then_uses_exact_control(self):
        backend=Backend();events=[];backend.emit=lambda **event:events.append(event)
        active={'address':'0x1','pid':42,'title':'Notes','class':'notes'}
        task={'action':'click','target':'Save'}
        with patch('hyprash.browser.run',return_value=json.dumps(active)), \
             patch.object(desktop,'inspect',return_value=self.observation), \
             patch.object(desktop,'select_control',return_value=self.observation['controls'][1]) as select, \
             patch.object(desktop,'control',return_value={'message':'Activated Save','verified':False,'evidence':'Action dispatched'}) as control:
            self.assertTrue(backend.execute(Action('ui_control',json.dumps(task))))
        select.assert_called_once_with(self.observation,task)
        control.assert_called_once_with({**task,'control':self.observation['controls'][1]},owner=self.owner)
        self.assertIn({'type':'execution','verified':False,'evidence':'Action dispatched','trace':[]},events)


if __name__ == '__main__':
    unittest.main()
