import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execution} from '../browser-extension/execution.js';

test('read-only readiness can retry; mutation is called once',async()=>{
 let time=0,observations=0,actions=0;
 const flow=execution({check:async()=>{},now:()=>time,sleep:async ms=>{time+=ms;}});
 await flow.observe('Wait for button',async()=>++observations===3);
 await flow.act('Click',async()=>{actions++;});
 assert.equal(observations,3);assert.equal(actions,1);
 assert.equal(flow.trace[0].elapsedMs,500);
 await assert.rejects(flow.act('Submit',async()=>{actions++;throw Error('Unknown outcome');}),/Unknown outcome/);
 assert.equal(actions,2);assert.equal(flow.trace.at(-1).attempts,1);
});
test('cancellation during observation exits before another read or action',async()=>{
 let cancelled=false,calls=0;
 const flow=execution({check:async()=>{if(cancelled)throw Error('Cancelled');}});
 await assert.rejects(flow.observe('Wait',async()=>{calls++;cancelled=true;return false;}),/Cancelled/);
 assert.equal(calls,1);assert.equal(flow.trace[0].status,'cancelled');
});
test('verification failure records timeout without retrying an action',async()=>{
 let time=0;
 const flow=execution({check:async()=>{},now:()=>time,sleep:async ms=>{time+=ms;}});
 await assert.rejects(flow.verify('Verify',async()=>false,500),/expected state/);
 assert.equal(flow.trace[0].status,'failed');assert.equal(flow.trace[0].elapsedMs,500);
});
