"""Export reviewed measurements without raw iperf host/session metadata."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('destination', type=Path)
args = parser.parse_args()
original = json.loads(args.source.read_text())
fields = ('started_at_utc', 'base_url', 'did', 'bytes', 'expected', 'complete',
          'stop_reason', 'full_1tb_test', 'seconds', 'average_MiB_s',
          'average_Mbit_s', 'first_byte_seconds', 'sample_header_and_zero_data_check',
          'sha256', 'sha256_matches', 'download_to_iperf_percent', 'comparison_note')
reviewed = {key: original[key] for key in fields if key in original}
reference = original.get('sha256_reference', {})
reviewed['sha256_reference'] = {key: reference[key] for key in ('sha256', 'bytes', 'range', 'method') if key in reference}
baseline = original.get('iperf', {})
reviewed['iperf'] = {key: baseline[key] for key in ('started_at_utc', 'direction', 'parallel_streams', 'transport', 'Mbit_s', 'MiB_s', 'bytes', 'seconds', 'status') if key in baseline}
reviewed['publication_note'] = 'Selected original measurements; raw iperf client host, addresses and session identifier omitted.'
args.destination.parent.mkdir(parents=True, exist_ok=True)
with args.destination.open('x') as out:
    json.dump(reviewed, out, indent=2)
    out.write('\n')
print(args.destination)
