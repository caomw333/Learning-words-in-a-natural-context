import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

def vocab():
    return {'source':'test fixture','words':[{'id':f'{i:04d}','word':w,'meaning':'测试释义','review':False,'raw':w} for i,w in enumerate(['abandon','able','ability','aboard','abroad','absence','absorb','accept','access','accident','achieve','active'],1)]}
def paragraph(targets):
    opening=' '.join(targets)+'. '
    return opening+' '.join(['The student read a simple story in the library and wrote it carefully.']*12)

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=server.Store(Path(self.tmp.name),vocab()); self.store.config={**server.DEFAULT_CONFIG,'apiKey':'test-key'}
    def tearDown(self): self.tmp.cleanup()
    def seed_round(self):
        words=self.store.words()[:10]
        r={'id':'test-round','number':1,'createdAt':server.now(),'status':'generating','mode':'mixed','theme':'library','words':[{k:w[k] for k in ['id','word','meaning']} for w in words],'articles':[],'requests':[],'error':''}
        self.store.state['rounds'].append(r); self.store.archive(r); return r
    def test_selection_ratio_excludes_pending_mastered_and_preserves_shortage(self):
        words=self.store.words()
        for w in words[:6]: w.update(occurrences=2,roundCount=1,lastSeen='2026-01-01')
        words[0]['status']='mastered';words[-1]['review']=True
        chosen=server.select_words(words,10,40,1,9999)
        self.assertEqual(len(chosen),10)
        self.assertEqual(sum(w['occurrences']>0 for w in chosen),5) # only five new available
        self.assertNotIn('0001',[w['id'] for w in chosen]);self.assertNotIn('0012',[w['id'] for w in chosen])
        chosen=server.select_words(words,8,50,1,9999)
        self.assertEqual(sum(w['occurrences']>0 for w in chosen),4)
    def test_exact_word_matching_and_variants(self):
        self.assertEqual(server.count_word('able unable able-bodied ABLE','able'),2)
        self.assertEqual(server.count_word('colour color colourful','colo(u)r'),2)
        self.assertEqual(server.count_word('accept accepted acceptance','accept'),1)
    def test_missing_words_not_counted_and_archives_survive_restart(self):
        r=self.seed_round(); target=r['words'][:2]
        reply={'choices':[{'message':{'content':json.dumps({'title':'A library day','body':paragraph([w['word'] for w in target])})},'finish_reason':'stop'}]}
        with patch('server.api_request',return_value=reply): server.run_generation(self.store,r['id'],[r['words']],self.store.config)
        self.assertEqual(r['status'],'needs_attention'); self.assertEqual(len(server.coverage(r)),2)
        self.assertEqual(self.store.words()[0]['selectedCount'],1);self.assertEqual(self.store.words()[2]['occurrences'],0)
        self.assertTrue((Path(self.tmp.name)/'rounds/test-round.md').exists())
        restored=server.Store(Path(self.tmp.name),vocab());self.assertEqual(restored.words()[0]['roundCount'],1)
        self.assertEqual(restored.state['rounds'][0]['articles'][0]['body'],r['articles'][0]['body'])
        self.assertNotIn('test-key',json.dumps(restored.public()))
    def test_valid_full_generation_and_copy_state(self):
        r=self.seed_round()
        reply={'choices':[{'message':{'content':json.dumps({'title':'A different day','body':paragraph([w['word'] for w in r['words']])})},'finish_reason':'stop'}]}
        with patch('server.api_request',return_value=reply): server.run_generation(self.store,r['id'],[r['words']],self.store.config)
        self.assertEqual(r['status'],'complete')
        server.action(self.store,'/api/copied',{'id':r['id'],'articleId':r['articles'][0]['id'],'copied':True})
        self.assertTrue(server.Store(Path(self.tmp.name),vocab()).state['rounds'][0]['articles'][0]['copied'])
    def test_malformed_response_preserved_and_not_retried(self):
        r=self.seed_round(); reply={'choices':[{'message':{'content':'invalid json'},'finish_reason':'stop'}]}
        with patch('server.api_request',return_value=reply) as request: server.run_generation(self.store,r['id'],[r['words']],self.store.config)
        self.assertEqual(request.call_count,1);self.assertEqual(r['status'],'needs_attention');self.assertEqual(r['requests'][0]['response'],reply);self.assertEqual(r['articles'],[])
    def test_no_key_does_not_create_round(self):
        self.store.config['apiKey']=''
        with self.assertRaises(ValueError):server.action(self.store,'/api/round',{'ids':['0001']})
        self.assertEqual(len(self.store.state['rounds']),0)
    def test_shuffle_same_batch_changes_order(self):
        words=self.store.words();ids=[w['id'] for w in words]
        shuffled=server.shuffle(words,ids)
        self.assertCountEqual(ids,[w['id'] for w in shuffled]);self.assertNotEqual(ids,[w['id'] for w in shuffled])
    def test_restart_marks_unfinished_request_unknown(self):
        r=self.seed_round();r['requests']=[{'wordIds':['0001'],'status':'sending'}];self.store.archive(r)
        restored=server.Store(Path(self.tmp.name),vocab())
        self.assertEqual(restored.state['rounds'][0]['status'],'interrupted');self.assertEqual(restored.state['rounds'][0]['requests'][0]['status'],'unknown')
    def test_lookup_local_and_remote_cache(self):
        with patch('server.api_request') as req:
            self.assertEqual(server.lookup_word(self.store,{'word':'ABLE'})['source'],'本地词库')
            req.assert_not_called()
        reply={'choices':[{'message':{'content':json.dumps({'word':'reading','meaning':'n. 阅读；read 的现在分词'})}}]}
        with patch('server.api_request',return_value=reply) as req:
            first=server.lookup_word(self.store,{'word':'reading'})
            second=server.lookup_word(self.store,{'word':'reading'})
            self.assertEqual(first['meaning'],second['meaning']);self.assertEqual(req.call_count,1)
            self.assertEqual(second['source'],'本地查询缓存')
        self.assertNotIn('test-key',(Path(self.tmp.name)/'dictionary-cache.json').read_text(encoding='utf-8'))
        for word in ['hello world','<script>','']:
            with self.assertRaises(ValueError):server.lookup_word(self.store,{'word':word})

    def test_bad_settings_and_selection_rejected(self):
        for count in [0,91,'a',3.5]:
            with self.assertRaises(ValueError):server.action(self.store,'/api/select',{'count':count})
        with self.assertRaises(ValueError):server.action(self.store,'/api/config',{'baseUrl':'http://evil.test','model':'model'})
        with self.assertRaises(ValueError):server.action(self.store,'/api/round',{'ids':['0001','0001']})

if __name__=='__main__': unittest.main()
