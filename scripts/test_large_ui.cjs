const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
async function scenario(mode) {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {value:'268435456', disabled:false, textContent:'', handlers:{}, addEventListener(event, cb){this.handlers[event]=cb;}});
    return elements.get(id);
  };
  const calls = [];
  const origin = 'http://64.176.188.89:18080';
  const size = 1000000005120;
  let reads = 0;
  const context = {
    document:{getElementById:get}, location:{origin}, performance, URL, AbortController,
    setTimeout:()=>1, clearTimeout:()=>{}, window:{confirm:()=>false},
    DOMParser: class { parseFromString() {return {getElementsByTagNameNS(){return [{getAttribute:()=> 'product-streamer',getElementsByTagNameNS(){return [{getAttribute:n=>n==='name'?'accessURL':origin+'/streamer/v1/data/product'}];}}];}};} },
    fetch:async (url, options={}) => {
      calls.push({url, options});
      if (url === '/lab/large/info') return {ok:true, json:async()=>({did:'lab.test:large-1tb.fits',bytes:size,allocated_bytes:4096})};
      if (url.startsWith('/datalink/')) return {ok:true,text:async()=>'<VOTABLE/>'};
      assert.equal(options.headers.Range,'bytes=0-268435455');
      let remaining=268435456;
      return {status:206,headers:{get:n=>({'content-length': mode==='bad-length'?'1':'268435456','content-range':`bytes 0-268435455/${size}`}[n]??null)},
        body:{getReader(){return {read:async()=>{reads++;if(!remaining)return {done:true};const length=Math.min(65536,remaining);remaining-=length;return {done:false,value:{byteLength:length}};},cancel:async()=>{}};}}};
    }
  };
  vm.runInNewContext(fs.readFileSync('lab/static/large.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(get('large-start').disabled,false);
  if(mode==='full-denied') get('large-size').value='full';
  await get('large-start').handlers.click();
  if(mode==='full-denied') assert.equal(calls.length,1);
  else if(mode==='bad-length') { assert.equal(reads,0); assert.match(get('large-progress').textContent,/Unexpected Content-Length/); }
  else { assert.match(get('large-progress').textContent,/Sample complete \(not a full 1 TB test\)/); assert.equal(reads,4097); }
  assert.equal(get('large-start').disabled,false);
}
(async()=>{for(const mode of ['sample','bad-length','full-denied']) {await scenario(mode);console.log('PASS',mode);}})().catch(e=>{console.error(e);process.exit(1);});
