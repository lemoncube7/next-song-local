import sys,unittest,json,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import video_kind
import core
from test_app import history,V1,V2,V3

class VideoKindTests(unittest.TestCase):
    def test_full_run_parks_streams_preserves_activity_references_and_reopens_changed_types(self):
        with tempfile.TemporaryDirectory() as folder:
            db=core.connect(Path(folder)/'db.sqlite3')
            core.import_bytes(db,json.dumps([history(V1,title='Minecraft gameplay',channel='Game'),history(V2,title='【歌枠】Karaoke',channel='Singer')]).encode(),'history.json')
            for vid,category in [(V1,'Gaming'),(V2,'Music')]:
                v=core.video_data(db,vid);v.update(category=category,metadata_status='ok',description='本家 https://youtu.be/'+V3+'\n00:12 Song / Artist');core.save_video(db,v)
            core.save_video(db,{'video_id':V3,'title':'Song','channel':'Artist - Topic','metadata_status':'ok'})
            row={'brand':'tj','no':'1','title':'Song','singer':'Artist'};db.execute('INSERT INTO catalogue VALUES (?,?,?)',('tj','1',json.dumps(row)))
            db.execute('CREATE TABLE whole_scan_tasks (id TEXT PRIMARY KEY,version TEXT,stage TEXT,data TEXT)')
            for vid,stage in [(V1,'unresolved'),(V2,'deep')]:db.execute('INSERT INTO whole_scan_tasks VALUES (?,?,?,?)',(vid,'test',stage,'{}'))
            core.rebuild(db);result=video_kind.run(db,threading.Lock())
            self.assertEqual(result['done'],2);self.assertEqual(result['counts']['activity'],1);self.assertEqual(result['counts']['collection'],1)
            self.assertEqual(db.execute('SELECT stage FROM whole_scan_tasks WHERE id=?',(V2,)).fetchone()[0],'collection')
            refs=json.loads(db.execute('SELECT data FROM recognition_results WHERE id=?',(V1,)).fetchone()[0]);self.assertEqual(refs['candidates'][0]['title'],'Song')
            v=core.video_data(db,V2);v['title']='Song / Artist';core.save_video(db,v);core.rebuild(db)
            self.assertEqual(video_kind.run(db,threading.Lock())['requeued'],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],2);db.close()
    def test_primary_purpose_and_identified_song_are_independent(self):
        v={'title':'Minecraft gameplay','category':'Gaming','classification':{'status':'song','title':'Background','artist':'Artist'}}
        r=video_kind.classify(v);self.assertEqual(r['kind'],'activity');self.assertTrue(r['has_identified_song'])
        self.assertNotEqual(r['confidence'],'category')

    def test_stream_lesson_and_cover_are_distinct(self):
        cases=[('【歌枠】KARAOKE','collection'),('기타 반주 레슨','music_explain'),('Song piano cover','song')]
        for title,kind in cases:self.assertEqual(video_kind.classify({'title':title,'category':'Music'})['kind'],kind)

    def test_category_is_a_provisional_claim_not_non_song_confirmation(self):
        r=video_kind.classify({'title':'Unclear','category':'Entertainment'})
        self.assertEqual(r['kind'],'activity');self.assertEqual(r['confidence'],'category')
        self.assertIn('확정은 아님',r['reason'])
        self.assertEqual(video_kind.classify({'title':'Deleted','metadata_status':'unavailable'})['kind'],'insufficient')

    def test_timestamp_mentions_are_extracted_without_playback_claim(self):
        rows={'song':[{'title':'Song','singer':'Artist','brand':'tj','no':'1'}]}
        v={'description':'00:12 Song / Artist\n01:30 Song / Other'}
        result=video_kind.mentions(v,rows,lambda _:None)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['artist'],'Artist');self.assertFalse(result[0]['confident'])

    def test_korean_original_credit_is_a_music_reference(self):
        v={'title':'번역 제목 / 원곡 가수','category':'People & Blogs','description':'본가 https://www.youtube.com/watch?v=abcdefghijk'}
        self.assertEqual(video_kind.classify(v)['kind'],'song')
        self.assertTrue(video_kind.classify(v)['has_original_reference'])
