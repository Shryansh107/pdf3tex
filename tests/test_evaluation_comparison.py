from copy import deepcopy

import pytest

from scripts.compare_evaluations import compare


def report():
    return {'manifest': {'inputs':[{'input':'a.pdf', 'sha256':'hash'}], 'pipeline_sha256':'pipeline'},
            'summary': {'layout':{}, 'portable':{}},
            'results': [{'input':'a.pdf', 'mode':mode, 'status':'success',
                         'metrics':{'similarity':92, 'matches':mode == 'portable'}}
                        for mode in ('layout', 'portable')]}


def test_comparison_counts_failures_as_zero_and_reports_regressions():
    before, after = report(), report()
    before['results'][0]['status'] = 'compile_failed'
    after['results'][1]['status'] = 'conversion_failed'
    after['results'][1].pop('metrics')
    result = compare(before, after)
    assert result['modes']['layout']['new_compiles'] == 1
    assert result['modes']['portable']['lost_compiles'] == 1
    assert result['modes']['portable']['lost_passes'] == 1
    assert result['changes'][0]['before_score'] == 0
    assert result['changes'][1]['delta'] == -92


def test_comparison_rejects_different_corpora_or_incomplete_records():
    before = report()
    after = deepcopy(before)
    after['manifest']['inputs'][0]['sha256'] = 'different'
    with pytest.raises(ValueError, match='same input'):
        compare(before, after)
    after = deepcopy(before)
    after['results'].pop()
    with pytest.raises(ValueError, match='both modes'):
        compare(before, after)
