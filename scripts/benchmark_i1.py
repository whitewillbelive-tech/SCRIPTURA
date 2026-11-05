#!/usr/bin/env python3
"""Complex synthetic D-3 benchmark. No research ZIP or production API overrides."""
from __future__ import annotations
import argparse, copy, json, multiprocessing as mp, os, platform, queue, resource, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'scripts')]
from s1b2_synthetic_factory import ACTIONS, TABLES, synthetic_rows
from i1_synthetic_factory import build_archive, synthetic_edges, synthetic_coverage
from d3_bridge.validator import validate_archive


def complex_input(target):
    # Each independent synthetic bundle adds linked sources, an edition, a checked
    # identity locator, all nine rights, two addresses and claims, evidence,
    # reviews, a relation, an affiliation, bibliographic citation and coverage.
    # Only wholly invented values are used. Size is total merged + auxiliary rows.
    base = synthetic_rows(12)
    delta = {name: [] for name in TABLES}
    edges = synthetic_edges()
    coverage = synthetic_coverage()
    base_total = sum(map(len, base.values())) + len(edges) + len(coverage)
    units = max(1, (target - base_total + 25) // 26)
    coverage_template = synthetic_coverage()[0]
    edge_template = synthetic_edges()[0]
    for i in range(units):
        s, other, ed, loc = f'src:scale-{i}-a', f'src:scale-{i}-b', f'ed:scale-{i}', f'loc:scale-{i}'
        p1, p2, ag, c1, c2 = f'passage:scale-{i}-a', f'passage:scale-{i}-b', f'agent:scale-{i}', f'claim:scale-{i}-a', f'claim:scale-{i}-b'
        work=f'Fictional Benchmark Unit {i}'
        for suffix, sid in [('a', s), ('b', other)]:
            delta['sources'].append({'id':sid,'title':f'Fictional source {i} {suffix}','kind':'book','creator':'Imaginary author','url':'https://example.invalid/source','doi':f'10.99999/fiction-scale-{i}-{suffix}'})
        delta['editions'].append({'id':ed,'source_id':s,'label':'Imaginary edition','language':'en','version_status':'partial'})
        delta['locators'].append({'id':loc,'edition_id':ed,'location':'Imaginary page','verification_status':'unchecked','checked_at':None})
        for action in ACTIONS:
            decision = 'allowed' if i % 20 == 0 and action in ('browse', 'collect_metadata') else ('conditional' if i % 5 == 0 else 'unknown')
            delta['rights'].append({'id':f'right:scale-{i}-{action}','edition_id':ed,'action':action,'decision':decision,'checked_at':'2026-01-01T00:00:00Z' if decision == 'allowed' else None,'evidence_url':'https://example.invalid/synthetic-rights' if decision == 'allowed' else None,'evidence_missing_reason':None if decision == 'allowed' else 'Synthetic only'})
        for pid, ref in [(p1,'1.1'),(p2,'1.2')]:
            delta['passages'].append({'id':pid,'corpus':'Imaginary corpus','work':work,'reference_scheme':'Imaginary scheme','reference':ref,'coverage_status':'partial'})
        delta['alignments'].append({'id':f'alignment:scale-{i}','from_passage_id':p1,'to_passage_id':p2,'alignment_type':'equivalent_segment','review_status':'partial_pending','locator_id':loc})
        delta['agents'].append({'id':ag,'name':f'Imaginary researcher {i}','kind':'person'})
        delta['affiliations'].append({'id':f'affiliation:scale-{i}','agent_id':ag,'tradition':'Fictional tradition','relation_kind':'self_identified','locator_id':loc,'official_doctrine_asserted':False,'review_status':'partial_pending'})
        for suffix,c,p in [('a',c1,p1),('b',c2,p2)]:
            delta['claims'].append({'id':c,'statement_ko':'합성 검증 자료','passage_ids':[p],'agent_id':ag,'attribution_kind':'individual_opinion','locator_id':loc,'review_status':'candidate','scope_note':'Synthetic only'})
            delta['evidence'].append({'id':f'evidence:scale-{i}-{suffix}','claim_id':c,'role':'context','locator_id':loc,'review_status':'proposed','explanation_ko':'합성 근거'})
            delta['reviews'].append({'id':f'review:scale-{i}-{suffix}','target_type':'claim','target_id':c,'reviewer':'Fictional reviewer','decision':'candidate','reviewed_at':'2026-01-01T00:00:00Z','notes':'Synthetic only'})
        delta['relations'].append({'id':f'relation:scale-{i}','from_claim_id':c1,'to_claim_id':c2,'relation_type':'qualifies','locator_id':loc,'review_status':'proposed','rationale_ko':'합성 관계'})
        edge=copy.deepcopy(edge_template);edge.update(id=f'bib:scale-{i}',from_source_id=s,to_source_id=other,locator_id=loc);edges.append(edge)
        item=copy.deepcopy(coverage_template);item.update(id=f'coverage:scale-{i}',work_label=work,d2_passage_records=0,d2_claim_links=0,d2_address_coverage='not_recorded',d3_merged_passage_records=2,d3_merged_claim_links=2,d3_address_coverage='partial');coverage.append(item)
    return base,delta,edges,coverage,units


def generation(target,path,q):
    try:
        started=time.monotonic();base,delta,edges,coverage,units=complex_input(target)
        sha,baseline,counts=build_archive(path,base_rows=base,delta_rows=delta,edges=edges,coverage=coverage)
        q.put({'status':'pass','target':target,'bundles':units,'archive_sha256':sha,'baseline_sha256':baseline,'counts':counts,'auxiliary_counts':{'bibliographic_edges':len(edges),'coverage':len(coverage)},'archive_bytes':Path(path).stat().st_size,'seconds':round(time.monotonic()-started,3),'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
    except BaseException as exc:q.put({'status':'fail','error_type':type(exc).__name__})


def validation(path,g,q):
    try:
        started=time.monotonic()
        report,records=validate_archive(path, expected_sha256=g['archive_sha256'], expected_baseline_sha256=g['baseline_sha256'],expected_counts=g['counts'], expected_auxiliary_counts=g['auxiliary_counts'],allow_synthetic=True)
        count=sum(len(v) for v in records.values());elapsed=round(time.monotonic()-started,3)
        expected=sum(g['counts'].values())+sum(g['auxiliary_counts'].values())
        rights=report.get('rights',{})
        rights_ok=all(rights.get(action,{}).get('effective_allowed')==0 for action in ACTIONS)
        good=report.get('status')=='pass' and count==expected and count>=g['target'] and rights_ok
        q.put({'status':'pass' if good else 'fail','expected_rows':expected,'all_nine_rights_denied':rights_ok,'seconds':elapsed,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'total_rows':count,'errors':report.get('errors',{}),'dispositions':report.get('dispositions',{})})
    except BaseException as exc:q.put({'status':'fail','error_type':type(exc).__name__})


def run_process(ctx,func,*args):
    q=ctx.Queue();p=ctx.Process(target=func,args=(*args,q));p.start();p.join(600)
    if p.is_alive():p.terminate();p.join();return {'status':'fail','error_type':'timeout'}
    if p.exitcode:return {'status':'fail','error_type':'worker_failed','exit_code':p.exitcode}
    try:return q.get(timeout=5)
    except queue.Empty:return {'status':'fail','error_type':'no_result'}
    finally:q.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--records',type=int,choices=(10000,100000),required=True);args=parser.parse_args()
    ctx=mp.get_context('spawn')
    with tempfile.TemporaryDirectory(prefix='scriptura-i1-synthetic-scale-') as d:
        path=str(Path(d)/'synthetic.zip');g=run_process(ctx,generation,args.records,path);v=run_process(ctx,validation,path,g) if g.get('status')=='pass' else {'status':'skipped','reason':'generation_failed'}
    result={'kind':'synthetic_only','target_records':args.records,'python':platform.python_version(),'platform':platform.platform(),'cpu_count':os.cpu_count(),'measurement':'Independent invented bundles; metadata, graph, rights and references scaled together; source/DB performance is not measured.','generation':g,'validation':v,'status':'pass' if g.get('status')==v.get('status')=='pass' else 'fail'}
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True));return 0 if result['status']=='pass' else 1

if __name__=='__main__':raise SystemExit(main())
