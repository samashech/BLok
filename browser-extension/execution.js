// A task-local trace. Only observation callbacks may be polled; actions run once.
export function execution({check, progress=()=>{}, now=()=>Date.now(), sleep=ms=>new Promise(r=>setTimeout(r,ms)), budget=40000}) {
  const trace=[], deadline=now()+budget;
  async function guard() {
    await check();
    if(now()>=deadline)throw Error('The task timed out. No remaining steps were run.');
  }
  async function stage(kind, label, fn, timeout=15000) {
    const started=now(), entry={kind,label,status:'running',attempts:0,elapsedMs:0};
    trace.push(entry);
    progress({message:label,kind,status:'running',stage:trace.length});
    try {
      const end=Math.min(deadline,started+timeout);
      let lastError;
      do {
        await guard();
        entry.attempts++;
        let result;
        if(kind==='act') result=await fn();
        else {
          try {result=await fn();lastError=undefined;}catch(error){lastError=error;}
        }
        await guard();
        if(kind==='act'||result){entry.status='complete';return result;}
        if(now()>=end)break;
        await sleep(Math.min(250,end-now()));
      }while(now()<end);
      throw Error(lastError?.message || 'The expected state was not observed.');
    }catch(error){
      entry.status=error.message==='Cancelled'?'cancelled':'failed';
      entry.error=error.message;
      throw Error(label+': '+error.message);
    }finally{
      entry.elapsedMs=Math.max(0,now()-started);
      progress({message:label,kind,status:entry.status,stage:trace.length,elapsedMs:entry.elapsedMs});
    }
  }
  return {trace,guard,
    observe:(label,fn,timeout)=>stage('observe',label,fn,timeout),
    act:(label,fn)=>stage('act',label,fn),
    verify:(label,fn,timeout)=>stage('verify',label,fn,timeout)};
}
