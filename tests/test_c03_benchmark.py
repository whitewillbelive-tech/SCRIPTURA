"""W11 C03 replay must never pretend that a dry run is a model answer."""
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from c03_benchmark import replay,search_from_question

class LookupTests(unittest.TestCase):
    def test_no_inferred_canon_or_fabricated_reference(self):
        class Index:
            def find(self,ref,limit=30):
                self.latest=(ref,limit)
                return [{'id':'p1','reference':ref,'claim_count':2},
                        {'id':'p2','reference':ref+'-other','claim_count':2}]
        index=Index()
        self.assertEqual(search_from_question('이사야 7:14에 관한 질문',index)[0][0]['id'],'p1')
        self.assertEqual(len(search_from_question('이사야 7:14에 관한 질문',index)[0]),1)
        self.assertEqual(search_from_question('다른 정경의 대응본문은?',index),([],None))

    def test_unrun_count_and_no_model_calls(self):
        class Index:
            def find(self,*a,**kw):
                return [{'id':'p1','reference':'Isaiah 7:14','claim_count':2}]
            def notes(self,*a,**kw):
                return [{'ref':'c1','statement':'SYNTHETIC','status':'local_research_input_unverified'}]
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'synthetic_qa.zip'
            with ZipFile(p,'w') as z:
                z.writestr('MANIFEST.json',json.dumps({'gate':'W11','canonical_sha256':'a'*64}))
                z.writestr('benchmark/questions.jsonl',''.join(json.dumps({'id':f'B{i:03d}','question':'이사야 7:14의 해석은?'},ensure_ascii=False)+'\n' for i in range(1,51)))
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            with patch('c04_benchmark.CanonicalIndex',return_value=Index()),patch('c04_benchmark.analyze_local') as m:
                out=replay('SYNTHETIC_CANONICAL',str(p),qa_expected_sha256=digest,canonical_expected_sha256='a'*64)
            self.assertEqual(out['questions'],50)
            self.assertEqual(out['model_called'],0)
            self.assertEqual(out['not_run'],50)
            self.assertEqual(out['independent_scores'],'NOT_SCORED')
            m.assert_not_called()

if __name__=='__main__':unittest.main()
