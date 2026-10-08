/* Stream to a bounded-memory discard sink. Never use arrayBuffer/blob on this product. */
(() => {
  const el = id => document.getElementById(id);
  let product, controller;
  const mib = n => (n / 1048576).toFixed(2);
  async function load() {
    try {
      const r = await fetch('/lab/large/info');
      if (!r.ok) throw Error(`Large fixture unavailable (HTTP ${r.status}).`);
      product = await r.json();
      el('large-info').textContent = `${product.did} · ${product.bytes.toLocaleString()} bytes · ${(product.bytes/1e12).toFixed(6)} TB logical size · ${product.allocated_bytes.toLocaleString()} bytes allocated on server`;
      el('large-start').disabled = false;
    } catch (e) { el('large-info').textContent = e.message; }
  }
  el('large-stop').addEventListener('click', () => controller?.abort());
  el('large-start').addEventListener('click', async () => {
    const full = el('large-size').value === 'full';
    if (full && !window.confirm('Transfer approximately 1 TB and discard it? This uses real public bandwidth and may incur charges.\n确认开始约 1 TB 公网传输？数据不保存，但会产生流量，可能收费。')) return;
    const expected = full ? product.bytes : Number(el('large-size').value);
    controller = new AbortController();
    const signal = controller.signal;
    let timer, reader, received = 0, first = 0, last = 0;
    const start = performance.now();
    el('large-start').disabled = true; el('large-size').disabled = true; el('large-stop').disabled = false;
    const progress = state => {
      const now = performance.now(), seconds = (now-start)/1000;
      const speed = received / Math.max(seconds, .001);
      el('large-progress').textContent = `${state} | ${mib(received)} / ${mib(expected)} MiB | ${seconds.toFixed(1)} s | average ${mib(speed)} MiB/s (${(speed*8/1e6).toFixed(2)} Mbit/s) | first byte ${first ? ((first-start)/1000).toFixed(2)+' s' : 'pending'} | bytes discarded, not saved; no full checksum`;
    };
    try {
      progress('Resolving DataLink');
      const discovery = await fetch('/datalink/v1/links?id='+encodeURIComponent(product.did), {signal});
      if (!discovery.ok) throw Error(`DataLink HTTP ${discovery.status}`);
      const xml = await discovery.text();
      const doc = new DOMParser().parseFromString(xml, 'application/xml');
      const resource = [...doc.getElementsByTagNameNS('*','RESOURCE')].find(x => x.getAttribute('ID') === 'product-streamer');
      const param = resource && [...resource.getElementsByTagNameNS('*','PARAM')].find(x => x.getAttribute('name') === 'accessURL');
      if (!param) throw Error('No Streamer descriptor');
      const url = new URL(param.getAttribute('value'));
      if (url.origin !== location.origin || url.pathname !== '/streamer/v1/data/product') throw Error('Unapproved Streamer URL');
      const headers = {'Content-Type':'application/xml', 'Authorization':'Bearer lab-service-token'};
      if (!full) headers.Range = `bytes=0-${expected-1}`;
      // Abort also protects against a stalled transfer. No server-side lifetime change.
      if (!full) timer = setTimeout(() => controller.abort(), expected > 268435456 ? 120000 : 30000);
      const r = await fetch(url.pathname, {method:'POST', headers, body:xml, signal});
      if (r.status !== (full ? 200 : 206)) throw Error(`Unexpected Streamer HTTP ${r.status}`);
      if (Number(r.headers.get('content-length')) !== expected) throw Error('Unexpected Content-Length');
      if (!full && r.headers.get('content-range') !== `bytes 0-${expected-1}/${product.bytes}`) throw Error('Unexpected Content-Range');
      if (r.headers.get('content-encoding') && r.headers.get('content-encoding') !== 'identity') throw Error('Compressed response cannot be used for this benchmark');
      reader = r.body.getReader();
      for (;;) {
        const {done, value} = await reader.read();
        if (done) break;
        received += value.byteLength;
        if (!first) first = performance.now();
        if (received > expected) throw Error('Transfer exceeded expected length');
        if (performance.now()-last > 250) { progress('Receiving'); last = performance.now(); }
      }
      if (received !== expected) throw Error('Incomplete response');
      progress(full ? 'Full transfer complete' : 'Sample complete (not a full 1 TB test)');
    } catch(e) { progress(e.name === 'AbortError' ? 'Stopped / time limit reached (partial test)' : e.message); }
    finally {
      clearTimeout(timer);
      if (reader) await reader.cancel().catch(()=>{});
      controller.abort(); controller = null;
      el('large-start').disabled = false; el('large-size').disabled = false; el('large-stop').disabled = true;
    }
  });
  load();
})();
