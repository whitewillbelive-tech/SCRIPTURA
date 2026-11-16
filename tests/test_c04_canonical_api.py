"""Synthetic C04 HTTP security and model input policy regression."""
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import j2_private_preview as api
from test_c03_canonical_local import synthetic_index, response

SECRET = 'synthetic-secret-123456789'
QUESTION = {'question':'Synthetic question', 'mode':'comparison', 'passage_id':'passage1'}

class CanonicalAPITests(unittest.TestCase):
    def setUp(self):
        self.index = synthetic_index()
        self.server = api.PrivatePreviewServer({'dataset':'D16','records':[],
                    '_canonical_index':self.index, '_local_model':'synthetic-model'}, SECRET)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join()

    def request(self, method, path, payload=None, headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        try:
            body=json.dumps(payload) if payload is not None else None
            conn.request(method,path,body=body,headers={'Host':self.server.expected_host,**(headers or {})})
            r=conn.getresponse();return r.status,dict(r.getheaders()),json.loads(r.read()) if r.status==200 else None
        finally:conn.close()

    def authorized(self):
        return {'Authorization':'Bearer '+SECRET,'Origin':self.server.expected_origin,'Content-Type':'application/json'}

    def test_no_permissions_means_no_model_request(self):
        with patch('urllib.request.build_opener') as opener:
            status, headers, data=self.request('POST','/api/canonical/analyze',QUESTION,self.authorized())
        self.assertEqual(status,200);self.assertIn('no-store',headers['Cache-Control'])
        self.assertEqual(data['status'],'model_input_not_permitted')
        self.assertEqual(data['notes'][0]['model_input_status'],'withheld')
        opener.assert_not_called()

    def test_authorized_local_model_gets_only_individually_allowed_fields(self):
        self.index._model_permission_check=lambda source,claim,card,locator,field,value: field=='statement'
        reply={'message':{'content':json.dumps({'analyses':[{'text':'Synthetic answer','citations':['claim1']}]})}}
        request_data=[]
        class Opener:
            def open(self,req,**kwargs):request_data.append(json.loads(req.data));return response(reply)
        with patch('urllib.request.build_opener',return_value=Opener()):
            status,_,data=self.request('POST','/api/canonical/analyze',QUESTION,self.authorized())
        self.assertEqual(status,200);self.assertEqual(data['status'],'analysis_unverified')
        sent=json.loads(request_data[0]['messages'][1]['content'])['input_notes']
        self.assertEqual(sent[0]['statement'],'Synthetic statement')
        self.assertNotIn('reasoning',sent[0])

    def test_model_list_requires_local_authorized_session(self):
        with patch('c04_ollama.list_local_models',return_value={'status':'ready','models':['synthetic-model'],'unsupported_count':0}) as listing:
            self.assertEqual(self.request('GET','/api/canonical/models')[0],401)
            listing.assert_not_called()
            status,headers,data=self.request('GET','/api/canonical/models',headers=self.authorized())
        self.assertEqual(status,200);self.assertIn('no-store',headers['Cache-Control'])
        self.assertEqual(data['selected_model'],'synthetic-model')

    def test_cross_origin_cannot_invoke_model(self):
        self.index._model_permission_check=lambda *args: True
        with patch('urllib.request.build_opener') as opener:
            self.assertEqual(self.request('POST','/api/canonical/analyze',QUESTION,
                {**self.authorized(),'Origin':'http://attacker.invalid'})[0],403)
            opener.assert_not_called()

if __name__=='__main__':unittest.main()
