import json,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,whole_recognition
from test_app import history,V1,V2,V3

class WholeRecognitionTests(unittest.TestCase):
    def test_all_videos_screened_deep_results_saved_and_resume_skips_completed(self):
        with tempfile.TemporaryDirectory() as folder:
            db=core.connect(Path(folder)/'db.sqlite3')
            core.import_bytes(db,json.dumps([history(V1,title='Artist「Original」 Music Video',channel='Artist'),history(V2,title='Mystery',channel='Uploader'),history(V3,title='Game update',channel='Gaming')]).encode(),'history.json')
            v=core.video_data(db,V2);v['category']='Music';core.save_video(db,v);core.rebuild(db)
            v=core.video_data(db,V3);v.update(category='Gaming',metadata_status='ok');core.save_video(db,v);db.commit()
            track={'title':'Mystery','artist':'Actual artist','reason':'Validated database ID','confident':True}
            with patch('whole_recognition.music_metadata.ensure') as music,patch('whole_recognition.references'),patch('whole_recognition.song_databases.search',return_value={'status':'recognized','track':track,'candidates':[track]}) as search:
                state=whole_recognition.run(db,lambda:'',threading.Lock(),threading.Event())
                self.assertEqual(state['status'],'complete');self.assertEqual(state['total'],3);self.assertEqual(state['done'],3)
                self.assertEqual(state['saved'],2);self.assertEqual(state['no_music_evidence'],1)
                self.assertEqual(music.call_count,1);self.assertEqual(search.call_count,1)
                before=core.get_state(db,'corrections',{},'user_state')
                second=whole_recognition.run(db,lambda:'',threading.Lock(),threading.Event())
                self.assertEqual(second['done'],3);self.assertEqual(search.call_count,1)
                self.assertEqual(core.get_state(db,'corrections',{},'user_state'),before)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],3);db.close()

    def test_explicit_original_pair_resolves_cover_without_accepting_other_singer(self):
        candidates=[{'title':'奏','artist':'スキマスイッチ','reason':'DB','confident':False}, {'title':'奏','artist':'Cover singer','confident':False}]
        result=whole_recognition.resolve({'title':'「奏 / スキマスイッチ」 - Cover singer（cover）'},{'status':'ambiguous','candidates':candidates})
        self.assertEqual(result['status'],'recognized');self.assertEqual(result['track']['artist'],'スキマスイッチ')
        result=whole_recognition.resolve({'title':'奏 cover'},{'status':'ambiguous','candidates':candidates})
        self.assertEqual(result['status'],'ambiguous')

    def test_stop_and_resume_retains_pending_and_protects_user_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            db=core.connect(Path(folder)/'db.sqlite3')
            core.import_bytes(db,json.dumps([history(V1,title='Mystery',channel='Uploader'),history(V2,title='Keep',channel='Uploader')]).encode(),'history.json')
            v=core.video_data(db,V1);v['category']='Music';core.save_video(db,v)
            core.set_state(db,'corrections',{V2:{'title':'Keep','artist':'Mine'}},'user_state');core.rebuild(db)
            stop=threading.Event();stop.set()
            state=whole_recognition.run(db,lambda:'',threading.Lock(),stop)
            self.assertEqual(state['status'],'stopped');self.assertEqual(state['local_remaining'],1)
            stop.clear()
            with patch('whole_recognition.music_metadata.ensure'),patch('whole_recognition.references'),patch('whole_recognition.song_databases.search',return_value={'status':'unresolved','candidates':[]}):
                state=whole_recognition.run(db,lambda:'',threading.Lock(),stop)
            self.assertEqual(state['status'],'complete');self.assertEqual(state['done'],1)
            self.assertEqual(core.get_state(db,'corrections',{},'user_state')[V2]['artist'],'Mine');db.close()
