import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';
const sandbox=vm.createContext({});
vm.runInContext(readFileSync(new URL('../ui/ThinkingOrbs.js',import.meta.url),'utf8'),sandbox);
for(const state of ['working','searching','solving','listening','connecting','weaving','composing','breathing','shaping']) {
  test(`native bundle produces finite ${state} geometry`,()=>{
    const a=sandbox.ThinkingOrbs.frame(state,.6);
    const b=sandbox.ThinkingOrbs.frame(state,1.2);
    assert.ok(a.dots.length>0);
    assert.notEqual(JSON.stringify(a),JSON.stringify(b));
    for(const d of [...a.dots,...b.dots]) {
      for(const key of ['x','y','z','r','white']) assert.ok(Number.isFinite(d[key]),key);
      assert.ok(d.r>0);
    }
  });
}
