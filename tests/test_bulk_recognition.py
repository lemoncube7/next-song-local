import json, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core, bulk_recognition

class BulkTests(unittest.TestCase):
    def test_whole_history_does_not_treat_news_or_games_as_songs(self):
        for category in ['Gaming','News & Politics']:
            self.assertFalse(bulk_recognition.music_evidence({'title':'New update - Channel','channel':'Channel','category':category},{'track':{'title':'New update','artist':'Channel'}}))
        self.assertTrue(bulk_recognition.music_evidence({'title':'Song / 初音ミク','category':'People & Blogs','description':'■曲、映像：Artist'},{'track':{}}))

    def test_full_run_persists_candidates_preserves_edits_and_stops_failed_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=core.connect(Path(tmp)/'db.sqlite3')
            rows=[{'title':title,'titleUrl':'https://www.youtube.com/watch?v='+vid,'time':'2026-10-10T08:00:00Z','subtitles':[{'name':channel}]} for vid,title,channel in [('abcdefghijk','Artist「Song」 Music Video','Artist'),('12345678901','Mystery','Fan'),('12345678902','Other','Fan'),('12345678903','Edited','Fan')]]
            core.import_bytes(db,json.dumps(rows).encode(),'history.json')
            for vid in ['12345678901','12345678902']:
                v=core.video_data(db,vid);v['category']='Music';core.save_video(db,v)
            core.set_state(db,'corrections',{'12345678903':{'title':'Keep','artist':'Mine'}},'user_state');db.commit();core.rebuild(db)
            with patch('bulk_recognition.google_search.search',return_value={'status':'unavailable','reason':'Unavailable','candidates':[]}) as google:
                result=bulk_recognition.run(db,lambda:'',threading.Lock())
                self.assertEqual(google.call_count,1)
            self.assertEqual(result['status'],'complete');self.assertEqual(result['done'],3);self.assertEqual(result['saved'],1)
            self.assertEqual(core.get_state(db,'corrections',{},'user_state')['12345678903']['title'],'Keep')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM recognition_results').fetchone()[0],3)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],4);db.close()

if __name__=='__main__':unittest.main()
