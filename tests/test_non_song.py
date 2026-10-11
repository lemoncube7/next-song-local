import sys,json,tempfile,threading,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,non_song
from test_app import history,V1,V2

class NonSongTests(unittest.TestCase):
    def test_two_positive_non_song_signals_required(self):
        v={'title':'Minecraft gameplay #shorts','category':'Gaming','metadata_status':'ok'}
        self.assertEqual(non_song.decide(v)['rule'],'gameplay')
        self.assertIsNone(non_song.decide({**v,'category':'Music'}))
        self.assertIsNone(non_song.decide({**v,'title':'Unclear title'}))
        self.assertIsNone(non_song.decide({**v,'metadata_status':'unavailable'}))

    def test_music_rhythm_and_original_links_are_protected(self):
        base={'category':'Gaming','metadata_status':'ok'}
        for title in ['Minecraft piano cover','[Arcaea] Song feat. 初音ミク','Minecraftで 原曲 cover','実況で歌ってみた']:
            self.assertIsNone(non_song.decide({**base,'title':title}))
        self.assertIsNone(non_song.decide({**base,'title':'Minecraft gameplay','description':'Original: https://youtu.be/abcdefghijk'}))
        self.assertIsNone(non_song.decide({**base,'title':'Minecraft gameplay'}, {'candidates':[{'title':'Minecraft','confident':True}]}))

    def test_background_music_is_not_standalone_song_and_metadata_change_invalidates(self):
        v={'title':'Minecraft gameplay','category':'Gaming','metadata_status':'ok','music_metadata':{'cards':[{'title':'Unrelated background','artist':'Other'}]}}
        decision=non_song.decide(v);v['non_song']=decision
        self.assertTrue(non_song.valid(v));self.assertEqual(core.classify(v)['status'],'non_song')
        v['title']='Minecraft song cover'
        self.assertFalse(non_song.valid(v));self.assertNotEqual(core.classify(v)['status'],'non_song')

    def test_reconcile_preserves_manual_and_does_not_delete_history(self):
        with tempfile.TemporaryDirectory() as folder:
            db=core.connect(Path(folder)/'db.sqlite3')
            core.import_bytes(db,json.dumps([history(V1,title='Minecraft gameplay',channel='Game'),history(V2,title='Minecraft gameplay',channel='Game')]).encode(),'history.json')
            for vid in (V1,V2):
                v=core.video_data(db,vid);v.update(category='Gaming',metadata_status='ok');core.save_video(db,v)
            core.set_state(db,'corrections',{V2:{'title':'Confirmed music','artist':'Artist'}},'user_state');core.rebuild(db)
            report=non_song.reconcile(db,threading.Lock())
            self.assertEqual(report['new_non_song'],1);self.assertEqual(core.video_data(db,V1)['classification']['status'],'non_song')
            self.assertEqual(core.video_data(db,V2)['classification']['status'],'song')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],2)
            self.assertEqual(non_song.reconcile(db,threading.Lock())['new_non_song'],0);db.close()
