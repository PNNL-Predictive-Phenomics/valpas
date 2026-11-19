"""Run the opt-in production CLI on tiny synthetic measurements, without training.

Uses the installed package when invoked with Python -I. Fixtures and this example
ship in the sdist. All generated files are temporary unless --outdir is supplied.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def demonstrate(root):
    from valpas.comparison import export_comparison_inputs, load_input_bundle
    root.mkdir(parents=True, exist_ok=True)
    source = root / 'synthetic__multiomics.csv'
    source.write_text('id,S01,S02,S03,S04,S05,S06\nM01,1,2,3,4,5,6\nM02,6,3,4,2,5,1\nP01,2,4,6,8,10,12\nP02,6,5,4,3,2,1\nP03,1,3,2,6,4,5\n')
    fixture = Path(__file__).resolve().parents[1] / 'tests/comparison/fixtures/demo-01/manifest.json'
    d = json.loads(fixture.read_text())['outputs'][0]
    d['identity']['dataset_id'] = 'b3-synthetic-measurements'
    d['identity']['context'] = 'Six synthetic observations, measured by the example only.'
    d['identity']['dataset_evidence'] = {
        'type': 'attestation', 'source': 'example generated measurements',
        'value': 'SHA256 of exact input bytes: ' + hashlib.sha256(source.read_bytes()).hexdigest(),
        'limitations': 'Caller-supplied identity; not a fingerprint of internal transformed arrays.'}
    d['configuration'] = {'parameters': None, 'preprocessing': None,
                          'score_semantics': 'signed Pearson correlation',
                          'supervision': None, 'observation_selection': 'all six observations',
                          'training_features': None}
    d['provenance'] = {'software': 'VaLPAS production CLI', 'source': str(source),
                       'limitations': 'Synthetic example, no model training or biological claim.'}
    d['count_semantics'] = 'Legacy pandas corr callable counts; diagonal is pandas unity, not an observation count.'
    request = root / 'request.json'
    destination = root / 'comparison-input'
    request.write_text(json.dumps({'descriptor': d, 'query_axis': 'index',
                                  'destination': str(destination.resolve())}, indent=2))
    python = [sys.executable] + (['-I'] if sys.flags.isolated else [])
    subprocess.run([*python, '-m', 'valpas.cli', 'associate', 'from_file', '--csv',
                    '--infile', str(source), '--association_type', 'pearson',
                    '--output_type', 'correlation_matrix', '--outfile', str(root / 'legacy.csv'),
                    '--comparison-export', str(request)], check=True)
    output = load_input_bundle(destination).outputs[0]
    assert output.pair('M01', 'P01').score == 1.0
    assert output.pair('M01', 'P02').score == -1.0
    assert output.descriptor['seed'] is None
    assert output.descriptor['configuration']['parameters']['valpas_method'] == 'pearson'
    assert output.descriptor['configuration']['preprocessing']['valpas_cli']['zero_to_missing'] is True
    d.update(output_id='spearman-run', method_id='spearman',
             configuration_id='spearman-base', run_id='spearman-run', label='Spearman')
    d['configuration']['score_semantics'] = 'signed Spearman correlation'
    second = root / 'spearman-input'
    request.write_text(json.dumps({'descriptor': d, 'query_axis': 'index',
                                  'destination': str(second.resolve())}, indent=2))
    subprocess.run([*python, '-m', 'valpas.cli', 'associate', 'from_file', '--csv',
                    '--infile', str(source), '--association_type', 'spearman',
                    '--output_type', 'correlation_matrix', '--outfile', str(root / 'spearman.csv'),
                    '--comparison-export', str(request)], check=True)
    combined = export_comparison_inputs([output, load_input_bundle(second).outputs[0]], root / 'combined-inputs')
    subprocess.run([*python, '-m', 'valpas.cli', 'compare', '--manifest',
                    str(combined / 'manifest.json'), '--outdir', str(root / 'comparison')], check=True)
    print('Production sidecar and comparison verified:', root)
    print('Legacy publication is independent. No training, rescoring, or checkpoint loading by export.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path)
    args = parser.parse_args()
    if args.outdir is not None:
        if args.outdir.exists():
            parser.error('--outdir must be new')
        demonstrate(args.outdir.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='valpas-b3-example-') as tmp:
            demonstrate(Path(tmp))


if __name__ == '__main__':
    main()
