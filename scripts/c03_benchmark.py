"""C-03 W11 replay harness: uses question text, NOT the grading oracle.

Needs user-owned W10R canonical ZIP and prior W11 QA ZIP. Actual Ollama
inference is opt-in. All output is local and does not grade correctness.
"""
import argparse
import json
from pathlib import Path
import re
from zipfile import ZipFile, BadZipFile
from c03_canonical_local import CanonicalIndex, CanonicalError, analyze_local

BOOK_MAP = (
    ('이사야 7:14','Isaiah 7:14'),
    ('요한복음 1:1','John 1:1'),
    ('마태복음 16:18','Matthew 16:18'),
    ('로마서 3:28','Romans 3:28'),
    ('야고보서 2:24','James 2:24'),
    ('창세기 1:1','Genesis 1:1'),
)
ALLOWED_CATEGORIES = {'same_passage','original_language','argument_counterargument',
                      'method_uncertainty','false_officialness','insufficient_evidence',
                      'injection','canon_alignment','rights','attribution'}

def search_from_question(question, index):
    # Exact book/address cue only, not guessing different canon or translation.
    if not isinstance(question,str) or len(question)>1000:
        return [], None
    ref = next((en for ko,en in BOOK_MAP if ko in question),None)
    if ref is None:
        # No default passage: missing context must remain NOT_RUN rather than
        # artificially presenting a different scripture's evidence.
        return [],None
    found=[row for row in index.find(ref,limit=30) if row['reference']==ref]
    return found,ref

def replay(canonical, audit, *, model=None, output=None):
    index=CanonicalIndex(canonical)
    with ZipFile(audit) as z:
        manifest=json.loads(z.read('MANIFEST.json'))
        if manifest.get('gate')!='W11':
            raise CanonicalError('wrong_audit_archive')
        questions=[json.loads(line) for line in z.read('benchmark/questions.jsonl').decode('utf-8').splitlines() if line.strip()]
    if len(questions)!=50 or len({q.get('id') for q in questions})!=50:
        raise CanonicalError('invalid_50_question_benchmark')
    results=[]
    for item in questions:
        matched,ref=search_from_question(item.get('question'),index)
        evidence=index.notes(matched[0]['id'],limit=8) if matched else []
        line={'id':item['id'],'status':'NOT_RUN','source_reference':ref,
              'matched_passages':len(matched),'evidence_candidates':len(evidence),
              'model_called':False}
        if model and evidence:
            line['model_called']=True
            try:
                answer=analyze_local(item['question'],'comparison',evidence,model)
                line.update(status=answer['status'],analysis=answer.get('analyses',[]))
            except CanonicalError as exc:
                line.update(status='MODEL_ERROR',error_code=str(exc))
        elif model:
            line.update(status='NOT_RUN_NO_LINKED_PASSAGE',reason='no exact source-backed passage')
        results.append(line)
    summary={'questions':50,'matched_question_count':sum(bool(r['matched_passages']) for r in results),
             'model_called':sum(r['model_called'] for r in results),
             'model_responded':sum(r['status']=='analysis_unverified' for r in results),
             'model_errors':sum(r['status']=='MODEL_ERROR' for r in results),
             'unrun':sum(r['status'].startswith('NOT_RUN') for r in results),
             'score':'NOT_SCORED_REQUIRES_INDEPENDENT_SOURCE_CHECK',
             'data_note':'W11 original benchmark oracle is not transmitted to models'}
    if output:
        path=Path(output)
        if path.exists():
            raise CanonicalError('output_already_exists')
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8') as f:
            for record in results:
                f.write(json.dumps(record,ensure_ascii=False)+'\n')
    return summary

def main(argv=None):
    p=argparse.ArgumentParser(description='SCRIPTURA W11 local model benchmark (no automatic grading)')
    p.add_argument('--canonical',required=True)
    p.add_argument('--audit',required=True)
    p.add_argument('--model',default=None,help='Opt in only to locally installed Ollama model')
    p.add_argument('--output',help='Private LOCAL results JSONL; will not overwrite')
    a=p.parse_args(argv)
    try:
        result=replay(a.canonical,a.audit,model=a.model,output=a.output)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (CanonicalError,FileNotFoundError,BadZipFile,KeyError,ValueError):
        print('W11_REPLAY_FAILED — confirm private inputs and local Ollama installation')
        return 1

if __name__=='__main__':
    raise SystemExit(main())
