const $ = id => document.getElementById(id);
let xml = '', endpoint = '', resolvedDid = '';
const fail = error => { $('message').textContent = error.message; };
function invalidate() { xml = ''; endpoint = ''; $('download').disabled = true; }
$('did').addEventListener('input', invalidate);
document.querySelectorAll('[data-did]').forEach(button => button.addEventListener('click', () => { $('did').value = button.dataset.did; invalidate(); }));
async function health() {
  try { const statuses = await (await fetch('/lab/status')).json(); statuses.forEach((s, i) => { const el = $(i ? 'ps-health' : 'dl-health'); el.textContent = s.http === 200 ? 'UP' : 'DOWN'; el.className = s.http === 200 ? '' : 'down'; }); }
  catch { $('dl-health').textContent = $('ps-health').textContent = 'unavailable'; }
}
$('resolve').addEventListener('click', async () => {
  invalidate(); $('resolve').disabled = true; $('message').textContent = 'Resolving the DID through the official DataLink service…';
  try {
    const response = await fetch('/datalink/v1/links?id=' + encodeURIComponent($('did').value.trim()));
    const text = await response.text(); $('xml').textContent = text; $('http-status').textContent = `DataLink HTTP ${response.status}`;
    if (!response.ok) throw new Error(`DataLink returned HTTP ${response.status}. Inspect the response.`);
    const parsed = new DOMParser().parseFromString(text, 'application/xml');
    if (parsed.getElementsByTagName('parsererror').length) throw new Error('Response is not parseable XML.');
    const resource = [...parsed.getElementsByTagNameNS('*', 'RESOURCE')].find(r => r.getAttribute('ID') === 'product-streamer');
    const param = resource && [...resource.getElementsByTagNameNS('*', 'PARAM')].find(p => p.getAttribute('name') === 'accessURL');
    if (!param) throw new Error('No Product Streamer descriptor was returned.');
    const discovered = new URL(param.getAttribute('value'));
    if (!['localhost', '127.0.0.1', '64.176.188.89'].includes(discovered.hostname) || discovered.port !== '18080' || discovered.pathname !== '/streamer/v1/data/product') throw new Error('Descriptor points outside the approved laboratory endpoint.');
    endpoint = discovered.pathname; xml = text; resolvedDid = $('did').value.trim();
    $('descriptor').textContent = `Discovered accessURL: ${discovered.href}`;
    $('message').textContent = 'Descriptor found. Send this VOTable to Streamer to test delivery.'; $('download').disabled = false;
  } catch(e) { fail(e); } finally { $('resolve').disabled = false; }
});
$('download').addEventListener('click', async () => {
  $('download').disabled = true; $('message').textContent = 'Requesting bytes from the official Streamer…';
  try {
    const headers = {'Content-Type':'application/xml'};
    if ($('auth').value) headers.Authorization = 'Bearer ' + $('auth').value;
    if ($('range').value.trim()) headers.Range = $('range').value.trim();
    const response = await fetch(endpoint, {method:'POST', headers, body:xml});
    $('http-status').textContent = `Streamer HTTP ${response.status}`;
    if (!response.ok) { $('xml').textContent = await response.text(); throw new Error(`Streamer returned HTTP ${response.status}; see the response inspector.`); }
    const buffer = await response.arrayBuffer();
    const hash = await labSha256(buffer);
    const evidence = {did:resolvedDid, http:response.status, bytes:buffer.byteLength, sha256:hash, content_type:response.headers.get('content-type'), content_range:response.headers.get('content-range')};
    $('xml').textContent = JSON.stringify(evidence,null,2);
    const name = response.headers.get('content-type')?.includes('tar') ? 'dataset.tar' : resolvedDid.split(':').slice(1).join(':');
    const blobURL = URL.createObjectURL(new Blob([buffer])); const link = document.createElement('a'); link.href=blobURL; link.download=response.status===206 ? name+'.partial' : name; link.click(); setTimeout(()=>URL.revokeObjectURL(blobURL),1000);
    $('message').textContent = `${buffer.byteLength.toLocaleString()} bytes received. SHA-256 recorded. ${response.status===206 ? 'Partial response; compare only the requested range.' : 'Compare with the fixture manifest or run the suite.'}`;
  } catch(e) { fail(e); } finally { $('download').disabled = !xml; }
});
$('run').addEventListener('click', async () => {
  $('run').disabled=true; $('summary').textContent='Running checks against both official services…'; $('export').hidden=true;
  try {
    const response=await fetch('/lab/run',{method:'POST'}); if(!response.ok)throw new Error(`Test runner HTTP ${response.status}`);
    const report=await response.json(); $('results').replaceChildren();
    report.results.forEach(result=>{const row=document.createElement('tr'); [result.name,result.status,result.http??'—',result.detail].forEach((value,i)=>{const cell=document.createElement('td');cell.textContent=value;if(i===1)cell.className=result.status;row.append(cell);});$('results').append(row);});
    $('summary').textContent=`${report.passed} / ${report.total} checks passed · ${report.timestamp}. Failures remain visible for investigation.`;
    $('export').href='/lab/reports/'+report.run_id+'.json'; $('export').hidden=false;
  } catch(e) {$('summary').textContent=e.message;} finally {$('run').disabled=false; health();}
});
(async()=>{try{const info=await(await fetch('/lab/info')).json();$('access-mode').textContent=location.hostname==='64.176.188.89'?'Password-protected public HTTP · synthetic data only':'SSH tunnel · private access';$('versions').textContent=`DataLink  ${info.datalink_commit}\nStreamer  ${info.streamer_commit}`;info.fixtures.forEach(f=>{const item=document.createElement('div');item.className='fixture';const name=document.createElement('strong');name.textContent=`${f.did} · ${f.bytes.toLocaleString()} bytes`;const hash=document.createElement('small');hash.textContent=f.sha256;item.append(name,hash);$('manifest').append(item);});}catch(e){fail(e);}health();})();
