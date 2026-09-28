import argparse
import asyncio
import hashlib
from importlib.metadata import version as package_version
import json
import re
import statistics
import subprocess
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.config import PROJECT_ROOT, get_settings
from backend.contracts import Snippet, parse_review_output
from backend.database import open_database
from backend.reviewer import OpenAIReviewer, SYSTEM_PROMPT
from backend.tracing import trace_subject


def grade(case, output):
    """Transparent candidate matching, not a semantic correctness oracle."""
    parsed = parse_review_output(output, case['code'])
    unmatched = set(range(len(parsed.findings)))
    matches = []
    for expected in case['expected']:
        for i in sorted(unmatched):
            finding = parsed.findings[i]
            text = finding.description + '\n' + (finding.suggested_fix or '')
            if (finding.category == expected['category']
                and finding.start_line <= expected['endLine'] and finding.end_line >= expected['startLine']
                and any(re.search(cue, text, re.I) for cue in expected['cues'])):
                matches.append({'issue': expected['id'], 'findingIndex': i, 'severityMatch': finding.severity in expected['severities']})
                unmatched.remove(i)
                break
    return {'matched': matches, 'missed': [e['id'] for e in case['expected'] if e['id'] not in {m['issue'] for m in matches}],
            'unmatchedFindings': sorted(unmatched), 'negativePass': not parsed.findings if not case['expected'] else None}


def summarize(rows):
    succeeded = [r for r in rows if r['status'] == 'succeeded']
    matched = sum(len(r['grade']['matched']) for r in succeeded)
    expected = sum(r['expectedCount'] for r in rows)
    returned = sum(len(r['output']['findings']) for r in succeeded)
    negatives = [r for r in rows if r['expectedCount'] == 0]
    severity = sum(m['severityMatch'] for r in succeeded for m in r['grade']['matched'])
    return {
        'attempts': len(rows), 'succeeded': len(succeeded), 'failed': len(rows)-len(succeeded),
        'expectedIssues': expected, 'returnedFindings': returned, 'heuristicMatches': matched,
        'candidatePrecision': matched / returned if returned else None,
        'candidateRecall': matched / expected if expected else None,
        'matchedSeverityAgreement': severity / matched if matched else None,
        'negativeCasesPassed': sum(r['status']=='succeeded' and r['grade']['negativePass'] is True for r in negatives),
        'negativeCaseAttempts': len(negatives),
        'medianLatencyMs': round(statistics.median(r['latencyMs'] for r in rows)) if rows else None,
        'inputTokens': sum(r.get('usage',{}).get('input_tokens') or 0 for r in rows),
        'outputTokens': sum(r.get('usage',{}).get('output_tokens') or 0 for r in rows),
        'usageAvailableAttempts': sum(r.get('usage',{}).get('input_tokens') is not None for r in rows),
    }


async def evaluate(args):
    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit('Set OPENAI_API_KEY in .env before running live evaluations.')
    cases_bytes = args.dataset.read_bytes()
    cases = json.loads(cases_bytes)
    if args.case:
        cases = [case for case in cases if case['id'] in args.case]
        if len(cases) != len(set(args.case)):
            raise SystemExit('Unknown or duplicate case selection.')
    if args.limit:
        cases = cases[:args.limit]
    prompt = args.prompt.read_text() if args.prompt else SYSTEM_PROMPT
    version = args.prompt.stem if args.prompt else OpenAIReviewer.prompt_version
    output_dir = args.output or PROJECT_ROOT / 'work/evals' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output_dir.mkdir(parents=True, exist_ok=False)
    settings = settings.model_copy(update={'database_path': output_dir / 'calls.db'})
    open_database(settings.database_path).close()
    reviewer = OpenAIReviewer(settings, prompt=prompt, prompt_version=version)
    rows=[]
    try:
        revision = subprocess.check_output(['git','rev-parse','HEAD'], cwd=PROJECT_ROOT, text=True).strip()
    except subprocess.SubprocessError:
        revision = None
    report = {'datasetSha256':hashlib.sha256(cases_bytes).hexdigest(), 'promptSha256':hashlib.sha256(prompt.encode()).hexdigest(),
              'promptVersion':version, 'model':settings.openai_model, 'gitRevision':revision,
              'gitDirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=PROJECT_ROOT,text=True).strip()),
              'openaiSdkVersion':package_version('openai'), 'startedAt':datetime.now(timezone.utc).isoformat(), 'repeats':args.repeats,
              'grading':'Line/category/keyword candidate matching. Manually inspect correctness, duplicates and fixes; this is not measured real-world accuracy.', 'rows':rows}
    (output_dir/'prompt.txt').write_text(prompt)
    (output_dir/'dataset.json').write_bytes(cases_bytes)
    for case in cases:
        for repeat in range(1,args.repeats+1):
            subject = f"eval:{case['id']}:{repeat}:{uuid4()}"
            snippet = Snippet(id=uuid4(),title=case['id'],language=case['language'],code=case['code'],created_at=datetime.now(timezone.utc))
            row={'caseId':case['id'],'repeat':repeat,'subjectId':subject,'expectedCount':len(case['expected'])}
            started=time.monotonic()
            try:
                with trace_subject(subject):
                    async with asyncio.timeout(settings.review_timeout_seconds):
                        result=await reviewer.review(snippet)
                row.update(status='succeeded',output=result.model_dump(mode='json',by_alias=True))
                row['grade']=grade(case,row['output'])
            except Exception as exc:
                row.update(status='failed',errorType=type(exc).__name__)
            row['latencyMs']=round((time.monotonic()-started)*1000)
            with closing(open_database(settings.database_path,migrate=False)) as db:
                call=db.execute('SELECT input_tokens,output_tokens FROM model_calls WHERE subject_id=? ORDER BY rowid DESC LIMIT 1',(subject,)).fetchone()
                row['usage']=dict(call) if call else {}
            rows.append(row)
            report['summary']=summarize(rows)
            (output_dir/'results.json').write_text(json.dumps(report,indent=2)+'\n')
            print(f"{case['id']} #{repeat}: {row['status']}",flush=True)
    print(json.dumps(report['summary'],indent=2))
    print('Results:',output_dir)
    if any(row['status']=='failed' for row in rows):
        raise SystemExit(1)


def main():
    parser=argparse.ArgumentParser(description='Opt-in live review evaluation; serial calls, no implicit retries.')
    parser.add_argument('--live',action='store_true',help='Allow billable provider calls for the selected fixtures')
    parser.add_argument('--dataset',type=Path,default=PROJECT_ROOT/'evals/cases.json')
    parser.add_argument('--prompt',type=Path,help='Optional prompt file for a baseline/candidate comparison')
    parser.add_argument('--case',action='append')
    parser.add_argument('--limit',type=int)
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not args.live:
        parser.error('No calls made. Use --live to explicitly enable provider calls.')
    if not 1 <= args.repeats <= 5 or (args.limit is not None and args.limit < 1):
        parser.error('repeats must be 1–5 and limit must be positive')
    asyncio.run(evaluate(args))


if __name__=='__main__':
    main()
