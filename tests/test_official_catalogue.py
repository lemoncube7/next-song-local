import json,sys,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,official_catalogue as official,official_providers as p,pipeline

class OfficialTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=core.connect(Path(self.tmp.name)/'test.db');official.ensure(self.db);core.set_state(self.db,'official_catalogue_enabled',True);self.db.commit()
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def row(self,**extra):return {'brand':'tj','no':'123','title':'Song','singer':'Artist','source':'official:tj','official_url':p.BASE['tj'],**extra}
 def track(self,**number):return {'id':'x','title':'Song','artist':'Artist','numbers':[{'brand':'tj','no':'123','title':'Song','artist':'Artist',**number}],'match_candidates':[]}
 def test_unofficial_candidate_never_becomes_official_by_flag(self):
  t=self.track(official_verified=True);official.overlay(self.db,[t],1000);self.assertEqual(t['numbers'],[]);self.assertEqual(len(t['match_candidates']),1)
 def test_matching_fresh_official_observation_required(self):
  official.store_result(self.db,('tj','title','Song'),[self.row()],1000);t=self.track();official.overlay(self.db,[t],1100);self.assertTrue(t['numbers'][0]['official_verified']);self.assertEqual(t['numbers'][0]['checked_at'],1000)
 def test_number_reused_for_different_song_not_verified(self):
  official.store_result(self.db,('tj','number','123'),[self.row(title='Other')],1000);t=self.track();official.overlay(self.db,[t],1100);self.assertFalse(t['numbers'])
 def test_stale_proof_moves_to_candidate_without_deleting_it(self):
  official.store_result(self.db,('tj','number','123'),[self.row()],1000);t=self.track();official.overlay(self.db,[t],1000+official.WEEK);self.assertFalse(t['numbers']);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM official_numbers').fetchone()[0],1)
 def test_future_not_offered_and_manual_preserved(self):
  official.store_result(self.db,('tj','number','123'),[self.row(release='2999-01-01')],1000);t=self.track();official.overlay(self.db,[t],1100);self.assertFalse(t['numbers']);t=self.track(source='manual');official.overlay(self.db,[t],1100);self.assertEqual(t['numbers'][0]['source'],'manual');self.assertFalse(t['numbers'][0]['official_verified'])
 def test_auxiliary_cache_expiry(self):
  from datetime import datetime,timezone,timedelta
  self.assertFalse(pipeline.catalogue_cached(json.dumps({'status':'ok'})));self.assertTrue(pipeline.catalogue_cached(json.dumps({'status':'ok','fetched_at':datetime.now(timezone.utc).isoformat()})));self.assertFalse(pipeline.catalogue_cached(json.dumps({'status':'ok','fetched_at':(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()})))
 def test_search_cache_and_resume(self):
  with patch('core.tracks',return_value=[{'title':'Song','history_records':1}]):
   self.assertIn(('tj','title','Song'),official.plan(self.db));official.store_result(self.db,('tj','title','Song'),[]);self.assertNotIn(('tj','title','Song'),official.plan(self.db))
 def test_tj_and_ky_parser(self):
  tj='<title>반주곡 검색</title><ul class="grid-container list"><li><span class="num2">123</span></li><li class="title3"><p>Song</p></li><li class="singer">Artist</li></ul>'
  self.assertEqual(p.parse_tj(tj,p.BASE['tj'])[0]['title'],'Song')
  ky='<ul class="search_chart_list"><li class="search_chart_num">123</li><li><span class="tit">Song</span><span class="tit mo-art">Other</span></li><li class="search_chart_sng">Artist</li><li class="search_chart_rel">2026.10</li></ul>'
  self.assertEqual(p.parse_ky(ky,p.BASE['kumyoung'])[0]['singer'],'Artist')
  with self.assertRaises(ValueError):p.parse_tj('<html>service error</html>','')
 def test_joy_uses_selectable_number_not_page_id(self):
  stream=json.dumps({'title':'Song','buttonsProps':[{'selSongNo':'123','naviGroupId':'999999','songName':'Song','artistName':'Artist'}]})
  page='JOYSOUND<script>self.__next_f.push('+json.dumps([1,stream])+')</script>'
  self.assertEqual(p.parse_joy(page,p.BASE['joysound'])[0]['no'],'123')
 def test_dam_future_and_models(self):
  doc={'result':{'statusCode':'0000'},'list':[{'requestNo':'1234-56','title':'Song','artist':'Artist','futureReleaseFlag':'1','releaseDate':'2999-01-01'}]}
  self.assertTrue(p.parse_dam(doc,'')[0]['future'])
 def test_failure_preserves_existing_proof(self):
  official.store_result(self.db,('tj','number','123'),[self.row()],1000);self.db.commit()
  with patch.object(official,'plan',return_value=[('tj','number','123')]),patch.object(p,'search',side_effect=TimeoutError):
   official.run(self.db,__import__('threading').Lock(),delay=0)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM official_numbers').fetchone()[0],1)

if __name__=='__main__':unittest.main()
