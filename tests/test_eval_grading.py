import json
from pathlib import Path

import pytest

from evals.run import grade, summarize

CASES=json.loads((Path(__file__).parents[1]/'evals/cases.json').read_text())


def test_candidate_matching_requires_category_lines_and_cue_and_counts_duplicates():
    case=CASES[0]
    finding={'startLine':2,'endLine':2,'severity':'critical','category':'bug','description':'Empty input divides by zero','suggestedFix':None}
    result=grade(case,{'findings':[finding,finding]})
    assert len(result['matched'])==1 and result['unmatchedFindings']==[1]
    assert result['matched'][0]['severityMatch'] is False
    for wrong in ({'startLine':1,'endLine':1},{'category':'style'},{'description':'Unrelated issue'}):
        result=grade(case,{'findings':[{**finding,**wrong}]})
        assert result['missed']==['empty-input'] and result['unmatchedFindings']==[0]
    with pytest.raises(ValueError):
        grade(case,{'findings':[{**finding,'endLine':999}]})


def test_negative_and_failed_attempts_not_hidden_in_summary():
    negative=next(case for case in CASES if case['id']=='safe-average')
    assert grade(negative,{'findings':[]})['negativePass'] is True
    rows=[{'status':'failed','expectedCount':1,'latencyMs':1},{'status':'failed','expectedCount':0,'latencyMs':2}]
    summary=summarize(rows)
    assert summary['failed']==2 and summary['candidateRecall']==0
    assert summary['negativeCasesPassed']==0 and summary['negativeCaseAttempts']==1
    assert summary['candidatePrecision'] is None and summary['usageAvailableAttempts']==0


def test_fixture_ids_and_expected_ranges_are_valid():
    assert len({case['id'] for case in CASES})==len(CASES)==10
    for case in CASES:
        for issue in case['expected']:
            assert 1 <= issue['startLine'] <= issue['endLine'] <= len(case['code'].splitlines())
            assert issue['description'] and issue['cues'] and issue['severities']
