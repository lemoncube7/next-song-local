import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,local_decision

class LocalDecisionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=core.connect(Path(self.tmp.name)/'test.sqlite3')
  self.v={'title':'Song / Artist cover','description':'Original: Song / Artist','classification':{'status':'review'}}
  self.c={'title':'Song','artist':'Artist','reason':'source','confident':False}
  self.r={'status':'ambiguous','candidates':[self.c],'reason':'review'}
  self.settings=patch('local_decision.config',return_value={'enabled':True,'endpoint':'http://127.0.0.1:11434','model':'test'});self.settings.start()
 def tearDown(self):self.settings.stop();self.db.close();self.tmp.cleanup()
 def test_selected_stays_review_and_reuses_cache(self):
  with patch('local_decision.choose',return_value={'choice':'C0','selected':self.c}) as choose:
   a=local_decision.enhance(self.db,self.v,self.r);b=local_decision.enhance(self.db,self.v,self.r)
   self.assertEqual(a['status'],'ambiguous');self.assertTrue(a['candidates'][0]['local_recommended']);self.assertFalse(a['candidates'][0]['confident']);self.assertTrue(b['local_decision']['cached']);self.assertEqual(choose.call_count,1)
   self.assertEqual(core.get_state(self.db,'corrections',{},'user_state'),{})
 def test_missing_candidate_does_not_force_match(self):
  with patch('local_decision.choose',return_value={'choice':'NONE','selected':None}):
   a=local_decision.enhance(self.db,self.v,self.r)
   self.assertEqual(a['local_decision']['status'],'no_match');self.assertNotIn('track',a)
 def test_unrelated_artist_is_not_sent(self):
  with patch('local_decision.choose') as choose:
   a=local_decision.enhance(self.db,{'title':'Unidentified clip','description':''},{'status':'unresolved','candidates':[self.c]})
   self.assertFalse(choose.called);self.assertEqual(a['local_decision']['status'],'no_candidates')
 def test_confirmed_and_excluded_are_preserved(self):
  with patch('local_decision.choose') as choose:
   for status in ('song','excluded','non_song'):
    v={**self.v,'classification':{'status':status}};self.assertEqual(local_decision.enhance(self.db,v,self.r),self.r)
   self.assertFalse(choose.called)
 def test_offline_keeps_candidates(self):
  with patch('local_decision.choose',side_effect=OSError('offline')):
   a=local_decision.enhance(self.db,self.v,self.r);self.assertEqual(a['candidates'],self.r['candidates']);self.assertEqual(a['local_decision']['status'],'unavailable')
 def test_changed_description_invalidates_cache(self):
  with patch('local_decision.choose',return_value={'choice':'NONE','selected':None}) as choose:
   local_decision.enhance(self.db,self.v,self.r);local_decision.enhance(self.db,{**self.v,'description':self.v['description']+' updated'},self.r);self.assertEqual(choose.call_count,2)
 def test_wrong_model_key_rejected(self):
  with patch('local_decision.chat',return_value={'message':{'content':'{"choice":"C99"}'}}):
   with self.assertRaises(ValueError):local_decision.choose(self.v,[self.c],{'endpoint':'http://127.0.0.1:11434'})
