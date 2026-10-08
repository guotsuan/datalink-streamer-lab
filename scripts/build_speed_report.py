"""Build a one-page English benchmark PDF and editable Markdown from actual evidence."""
import json
from pathlib import Path
import sys
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from pypdf import PdfReader

evidence = Path(sys.argv[1]).resolve()
r = json.loads(evidence.read_text())
root = Path(__file__).resolve().parents[1]
label = f'{r["expected"]/1e9:g}GB'
pdf = root / f'output/pdf/DataLink_Streamer_{label}_SHA256_Report_EN.pdf'
md = root / f'output/reports/DataLink_Streamer_{label}_SHA256_Report_EN.md'
pdf.parent.mkdir(parents=True, exist_ok=True)
md.parent.mkdir(parents=True, exist_ok=True)
passed = bool(r['complete'] and r['sha256_matches'] and r['sample_header_and_zero_data_check'])
baseline = r['iperf']
rows = [['Measurement', 'Result'],
    ['iperf3 receiver throughput', f'{baseline["Mbit_s"]:.3f} Mbps / {baseline["MiB_s"]:.3f} MiB/s'],
    ['iperf3 duration / received bytes', f'{baseline["seconds"]:.3f} s / {baseline["bytes"]:,} bytes'],
    ['Requested / received download bytes', f'{r["expected"]:,} / {r["bytes"]:,}'],
    ['Download duration', f'{r["seconds"]:.3f} s ({r["seconds"]/60:.2f} min)'],
    ['Download average throughput', f'{r["average_Mbit_s"]:.3f} Mbps / {r["average_MiB_s"]:.3f} MiB/s'],
    ['Time to first byte', f'{r["first_byte_seconds"]:.3f} s' if r['first_byte_seconds'] is not None else 'Not received'],
    ['Download / iperf3 throughput', f'{r["download_to_iperf_percent"]:.2f}%' if r['download_to_iperf_percent'] is not None else 'Not available'],
    ['Transfer completion', 'PASS' if r['complete'] else 'FAIL'],
    ['SHA-256 comparison', 'PASS' if r['sha256_matches'] else 'FAIL'],
    ['Synthetic header / zero-data check', 'PASS' if r['sample_header_and_zero_data_check'] else 'FAIL']]
title = f'DataLink and Product Streamer: {r["expected"]/1e9:g} GB Download and SHA-256 Test'
config = (f'A 10-second, single-stream reverse TCP iperf3 baseline was followed by a '
    f'{r["expected"]/1e9:g} GB download from the temporary VM to the client. DataLink resolved the synthetic '
    f'product; Product Streamer delivered bytes 0-{r["expected"]-1} from the approximately 1 TB sparse FITS source. '
    'The download had no total time limit. Blocks were hashed, checked and discarded. '
    'A reference SHA-256 was independently computed from the same byte range on the server before the network tests.')
integrity = ('The requested byte count and HTTP range were verified. The received SHA-256 matched the independently '
    'computed source-range digest; FITS header markers and zero-filled payload checks also passed. '
    'Verification covers the complete downloaded range.' if passed else
    'See the recorded transfer and integrity results above; a failed or incomplete test must not be reported as a verified download.')
text = f'# {title}\n\n**Download start (UTC):** {r["started_at_utc"]}\n\n**Endpoint:** {r["base_url"]} | **Product:** `{r["did"]}`\n\n## Test configuration\n\n{config}\n\n## Results\n\n'
text += '| Measurement | Result |\n|---|---:|\n' + '\n'.join(f'| {a} | {b} |' for a,b in rows[1:])
text += f'\n\n## Data integrity verification\n\n{integrity}\n\n**Received SHA-256:** `{r["sha256"]}`\n\n**Reference SHA-256:** `{r["sha256_reference"]["sha256"]}`\n\n**Evidence:** `{evidence}`\n'
md.write_text(text)
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='RTitle',fontName='Helvetica-Bold',fontSize=18,leading=22,textColor=colors.HexColor('#173b52'),spaceAfter=14))
styles.add(ParagraphStyle(name='RBody',fontSize=10.5,leading=14.5,spaceAfter=10))
styles.add(ParagraphStyle(name='RHead',fontName='Helvetica-Bold',fontSize=12,leading=15,textColor=colors.HexColor('#087f80'),spaceBefore=10,spaceAfter=7))
styles.add(ParagraphStyle(name='Digest',fontName='Courier',fontSize=8.8,leading=13,spaceAfter=8))
styles.add(ParagraphStyle(name='Evidence',fontSize=8.5,leading=12,textColor=colors.HexColor('#555555')))
story=[]
def p(s,style='RBody'): story.append(Paragraph(s,styles[style]))
p(f'DataLink and Product Streamer<br/>{r["expected"]/1e9:g} GB Download and SHA-256 Test','RTitle')
started = datetime.fromisoformat(r['started_at_utc']).strftime('%d %B %Y, %H:%M:%S UTC')
p(f'<b>Download start:</b> {started}<br/><b>Endpoint:</b> {r["base_url"]}<br/><b>Product:</b> {r["did"]}')
p('Test configuration','RHead'); p(config)
p('Results','RHead')
t=Table(rows,colWidths=[255,240],hAlign='LEFT')
t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#173b52')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9.5),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#edf4f8'),colors.white]),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d8e3ea'))]))
story.append(t)
p('Data integrity verification','RHead'); p(integrity)
p('Received SHA-256:<br/>'+r['sha256'],'Digest')
p('Reference SHA-256:<br/>'+r['sha256_reference']['sha256'],'Digest')
p('Evidence: '+str(evidence.relative_to(root)),'Evidence')
doc=SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=50,rightMargin=50,topMargin=40,bottomMargin=38,title=title)
doc.build(story)
assert len(PdfReader(pdf).pages)==1, 'Report must fit on one page'
print(pdf); print(md)
