import sys,tempfile,time,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,recommendation as r,mobile_transfer as mobile

def track(i,no,brand='tj',**extra):return {'id':i,'title':'Song '+i,'artist':'Artist','numbers':[{'brand':brand,'no':no,'source':'manual'}],'member_ids':[i],'aliases':[],'history_records':10,'last_watch':'2026-10-01','base_score':.3,'frequency_score':.2,'recency_score':.1,'video_ids':[i],'sources':['manual'],'match_candidates':[],**extra}
class RecommendationTests(unittest.TestCase):
 def test_brand_qualified_number_groups_preserve_input(self):
  items=[track('b','00123'),track('a','123'),track('c','123','dam')];original=copy.deepcopy(items);g=r.group_tracks(items);self.assertEqual(len(g),2);x=next(t for t in g if t['id']=='a');self.assertEqual(set(x['member_ids']),{'a','b'});self.assertEqual(x['history_records'],20);self.assertEqual(items,original)
 def test_bridge_is_transitive(self):
  b=track('b','2');c=track('c','1');c['numbers'].append({'brand':'tj','no':'2'});g=r.group_tracks([track('a','1'),b,c]);self.assertEqual(len(g),1);self.assertEqual(set(g[0]['member_ids']),{'a','b','c'})
 def test_different_song_rejection_wins(self):
  g=r.group_tracks([track('a','1'),track('b','1')],[{'source_members':['a'],'target_members':['b']}]);self.assertEqual(len(g),2)
 def test_boost_is_bounded_and_monotonic(self):
  self.assertEqual(r.boost(0),0);self.assertGreater(r.boost(2),r.boost(1));self.assertLessEqual(r.boost(1000000),.15)
 def test_reveal_debounce_and_mobile_idempotency(self):
  with tempfile.TemporaryDirectory() as folder:
   db=core.connect(Path(folder)/'test.sqlite3')
   import json
   for t in [track('a','123'),track('b','123')]:db.execute('INSERT INTO tracks VALUES (?,?)',(t['id'],json.dumps(t)))
   db.commit();now=int(time.time());sid=mobile.source_id(db)
   doc={'format':mobile.OPERATIONS,'version':1,'source_id':sid,'device_id':'f'*32,'operations':[{'id':'a'*32,'kind':'number_open','target':'b','value':now-1900},{'id':'b'*32,'kind':'number_open','target':'a','value':now-1850},{'id':'c'*32,'kind':'number_open','target':'a','value':now}]}
   self.assertEqual(mobile.apply(db,doc)['applied'],3);self.assertEqual(mobile.apply(db,doc)['duplicates'],3)
   t=core.tracks(db)[0];self.assertEqual(t['number_open_count'],2);self.assertAlmostEqual(t['number_open_score'],r.boost(2));self.assertEqual(len(core.tracks(db)),1);db.close()
if __name__=='__main__':unittest.main()
