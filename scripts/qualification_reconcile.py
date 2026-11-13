"""Read-only release reconciliation using TOFA's existing behaviour assessor.

No launch, discovery, live checks, receipt rewriting, or release authorization.
Legacy review bindings are verified and reported separately; they never silently
supply a missing assessor row. Model/catalog/cache identities are provenance.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from qualification_kit import digest, regular


def reference(base, ref):
    path = Path(ref['path'])
    if path.is_absolute():
        target = regular(path.parent, path.name)
    else:
        target = regular(base, ref['path'])
    if digest(target) != ref['sha256']:
        raise ValueError('evidence integrity mismatch')
    return target


def reconcile(path):
    plan = json.loads(path.read_text())
    if plan['schema'] != 'tofa-release-reconciliation-v1':
        raise ValueError('unsupported reconciliation schema')
    assessor = reference(path.parent, plan['assessor'])
    assessment = reference(path.parent, plan['assessment'])
    original = json.loads(assessment.read_text())
    if original['target'] != plan['target']:
        raise ValueError('assessment target differs from declared candidate')
    reviews = []
    for entry in plan.get('retained_reviews', []):
        review_path = reference(path.parent, entry['review'])
        review = json.loads(review_path.read_text())
        root = Path(entry['evidence_root'])
        if not root.is_absolute(): root = path.parent / root
        receipts = review['original_receipts_sha256']
        if not receipts:
            raise ValueError('retained review lacks original receipt bindings')
        for name, expected in receipts.items():
            reference(root, {'path':name, 'sha256':expected})
        if not entry['reviewer'].strip() or not entry['reason'].strip():
            raise ValueError('legacy review requires explicit attribution and reason')
        reviews.append({'review': entry['review'], 'receipts_verified': len(receipts),
                        'original_status': review.get('status'), 'reviewer':entry['reviewer'],
                        'reason':entry['reason'], 'supplies_assessor_coverage':False})
    completed = subprocess.run([str(assessor), 'desktop-qualification', 'assess',
        '--assessment', str(assessment)], capture_output=True, text=True, timeout=60)
    if completed.returncode:
        raise ValueError('behaviour assessor rejected the evidence; no reconciliation granted')
    assessed = json.loads(completed.stdout)
    if (assessed['schema'] != 'tofa-desktop-assessment-v1'
            or assessed['target'] != plan['target'] or assessed['release_qualified'] is not False):
        raise ValueError('unexpected assessor contract or candidate identity')
    dispositions = {'established':'accepted', 'reused':'reused',
                    'missing':'targeted_evidence_needed', 'failed':'investigate_failed_contract'}
    matrix = {}
    for behaviour, row in assessed['behaviours'].items():
        if row['status'] not in dispositions: raise ValueError('unknown assessor status')
        matrix[behaviour] = dict(row, disposition=dispositions[row['status']])
    # Output carries the authoritative result intact, not a second acceptance
    # policy. It is private evidence, not an automatically publishable summary.
    return {'schema':'tofa-release-reconciliation-result-v1', 'candidate':plan['candidate'],
            'declaration_sha256':digest(path), 'assessment':plan['assessment'],
            'assessor':plan['assessor'], 'matrix':matrix, 'assessor_result':assessed,
            'retained_reviews':reviews, 'provenance':plan.get('provenance', {}),
            'release_qualified':False, 'desktop_launches':0, 'paid_requests':0,
            'next_action':'review_combined_scope' if assessed['coverage_complete'] else 'resolve_listed_behaviours_only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--declaration', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    os.umask(0o077)
    try:
        # Reserve before execution; never overwrite any previous receipt/report.
        with options.output.open('x') as stream:
            result = reconcile(options.declaration.resolve())
            json.dump(result, stream, indent=2)
            stream.write('\n')
        print('Reconciliation retained; release authorization remains separate.')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('Reconciliation stopped: ' + str(error), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__': sys.exit(main())
