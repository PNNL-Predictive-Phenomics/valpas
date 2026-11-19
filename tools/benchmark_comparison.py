"""Bounded dense saved-score comparison smoke benchmark, not a training test.

Runs in a child process with parent RSS/time monitoring. A stopped run is a
measured limitation, never a passed scale gate. Output is an exclusive JSON
record; synthetic source files and child scratch data are temporary.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import tempfile
import time


def worker(args):
    from valpas.comparison import load_manifest, compare_results, ReportSettings
    from valpas.comparison.browser import build_report_payload
    root = Path(args.work)
    stage = root / 'progress.json'
    start = time.monotonic()
    def progress(name, **extra):
        record = {'stage': name, 'elapsed_seconds': time.monotonic() - start, **extra}
        temporary = root / 'progress.tmp'
        temporary.write_text(json.dumps(record))
        temporary.replace(stage)
    template = json.loads(Path(args.fixture).read_text())
    qs = [f'q{i:04d}' for i in range(args.queries)]
    cs = [f'c{i:05d}' for i in range(args.candidates)]
    manifest = {'schema_version': 1, 'dataset': template['dataset'], 'outputs': [],
                'settings': {'pool_policy': 'strict', 'depths': [5, 10, 20]}}
    manifest['dataset']['dataset_id'] = 'synthetic-b3-scale'
    for index in range(args.outputs):
        progress('generate_saved_scores', output=index)
        d = json.loads(json.dumps(template['outputs'][0]))
        d.update(output_id=f'output-{index}', configuration_id=f'config-{index}', run_id=f'run-{index}',
                 query_ids=qs, candidate_ids=cs, identity=manifest['dataset'])
        name = f'scores-{index}.csv'
        d['data'] = {'format': 'csv', 'path': name}
        manifest['outputs'].append(d)
        with (root / name).open('w') as handle:
            handle.write('query_id,' + ','.join(cs) + '\n')
            for q, qid in enumerate(qs):
                # Deterministic saved synthetic values; not an association fit.
                values = [str(((q * 31 + c * 17 + index * 997) % 100003 - 50001) / 50001)
                          for c in range(args.candidates)]
                handle.write(qid + ',' + ','.join(values) + '\n')
    (root / 'manifest.json').write_text(json.dumps(manifest))
    progress('load_manifest')
    loaded = load_manifest(root / 'manifest.json')
    progress('compare_results')
    result = compare_results(loaded)
    progress('bounded_report_payload')
    payload = build_report_payload(result, ReportSettings(query_ids=tuple(qs[:2]), max_interactive_depth=20))
    payload_bytes = len(json.dumps(payload).encode())
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    progress('completed', comparison_id=result.comparison_id, report_payload_bytes=payload_bytes,
             worker_peak_rss_bytes=peak if sys.platform == 'darwin' else peak * 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queries', type=int, default=1000)
    parser.add_argument('--candidates', type=int, default=5000)
    parser.add_argument('--outputs', type=int, default=8)
    parser.add_argument('--max-rss-mib', type=int, default=6144)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--record')
    parser.add_argument('--fixture', default='tests/comparison/fixtures/demo-01/manifest.json')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--work', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.queries, args.candidates, args.outputs, args.max_rss_mib, args.timeout) <= 0:
        parser.error('dimensions and limits must be positive')
    if args.worker:
        worker(args)
        return 0
    if not args.record:
        parser.error('--record is required')
    record_path = Path(args.record)
    # Reserve without overwriting an earlier measurement.
    with record_path.open('x') as handle:
        handle.write('{}\n')
    record = {'dimensions': [args.queries, args.candidates, args.outputs],
              'pair_count': args.queries * args.candidates * args.outputs,
              'max_rss_mib': args.max_rss_mib, 'timeout_seconds': args.timeout,
              'platform': platform.platform(), 'python': sys.version,
              'scope': 'dense CSV load, full comparison summaries, two-query report payload; no full bundle write',
              'status': 'running'}
    start = time.monotonic()
    peak = 0
    with tempfile.TemporaryDirectory(prefix='valpas-scale-') as tmp:
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--work', tmp,
                   '--queries', str(args.queries), '--candidates', str(args.candidates),
                   '--outputs', str(args.outputs), '--fixture', str(Path(args.fixture).resolve())]
        with (Path(tmp) / 'worker.log').open('w+') as log:
            process = subprocess.Popen(command, stdout=log, stderr=log)
            reason = None
            while process.poll() is None:
                sample = subprocess.run(['ps', '-o', 'rss=', '-p', str(process.pid)], capture_output=True, text=True)
                if sample.stdout.strip():
                    peak = max(peak, int(sample.stdout.strip()) * 1024)
                if peak > args.max_rss_mib * 1024 ** 2:
                    reason = 'rss_limit'
                elif time.monotonic() - start > args.timeout:
                    reason = 'time_limit'
                if reason:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    break
                time.sleep(.25)
            log.seek(0)
            record['worker_log'] = log.read()
        progress_path = Path(tmp) / 'progress.json'
        record['last_progress'] = json.loads(progress_path.read_text()) if progress_path.exists() else None
        record.update(status='bounded_stop' if reason else 'passed' if process.returncode == 0 else 'failed',
                      stop_reason=reason, returncode=process.returncode,
                      elapsed_seconds=time.monotonic() - start, sampled_peak_rss_bytes=peak)
    record_path.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    return 0 if record['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
