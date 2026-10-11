import sys,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,user_backup,recognition

class WorkflowTests(unittest.TestCase):
    def test_reuse_only_watched_and_unedited_videos_and_is_idempotent(self):
        from test_app import history,V1,V2,V3
        with tempfile.TemporaryDirectory() as folder:
            db=core.connect(Path(folder)/'db.sqlite3')
            core.import_bytes(db,json.dumps([history(V1,title='Song',channel='Artist'),history(V2,title='Artist - Song',channel='Artist'),history(V3,title='Artist - Song',channel='Artist')]).encode(),'history.json')
            core.set_state(db,'corrections',{V1:{'title':'Song','artist':'Artist','exclude':False},V3:{'exclude':True}},'user_state');core.rebuild(db)
            core.save_video(db,{'video_id':'reference01','title':'Artist - Song','channel':'Artist','classification':{'status':'review'}});db.commit()
            result=recognition.reuse_confirmed(db)
            self.assertEqual([e['video_id'] for e in result['items']],[V2])
            self.assertTrue(core.get_state(db,'corrections',{},'user_state')[V3]['exclude'])
            self.assertNotIn('reference01',core.get_state(db,'corrections',{},'user_state'))
            self.assertEqual(recognition.reuse_confirmed(db)['saved'],0);db.close()
    def test_backup_roundtrip_and_validation_preserve_state(self):
        with tempfile.TemporaryDirectory() as folder,patch('core.ROOT',Path(folder)):
            db=core.connect(Path(folder)/'db.sqlite3')
            state={'follows':['Artist'],'karaoke_ratings':{'song':-3},'different_songs':{'pair':{'source':'a','target':'b'}},'queue':['song']}
            for k,v in state.items():core.set_state(db,k,v,'user_state')
            db.commit();backup=user_backup.export(db)
            core.set_state(db,'follows',['Other'],'user_state');db.commit()
            restored=user_backup.restore(db,backup)
            self.assertEqual(user_backup.export(db)['user_state'],state)
            previous=json.loads((Path(folder)/'data/backups'/restored['previous_backup']).read_text(encoding='utf8'))
            self.assertEqual(previous['user_state']['follows'],['Other'])
            with self.assertRaises(ValueError):user_backup.restore(db,{**backup,'user_state':{'follows':{}}})
            self.assertEqual(core.get_state(db,'follows',[],'user_state'),['Artist']);db.close()

    def test_known_background_music_is_not_a_song_identity(self):
        t={'id':'one','title':'SUN OR SUCK','artist':'WOODZ','aliases':[]}
        v={'title':'트러플 머쉬룸 와퍼가 단종된 충격적인 이유','music_metadata':{'cards':[{'title':'SUN OR SUCK','artist':'WOODZ'}]}}
        self.assertIsNone(recognition.confirmed_identity(v,[t]))

    def test_number_match_uses_confirmed_alias_and_preserves_other_singer_candidate(self):
        rows=[{'title':'メフィスト','singer':'女王蜂','brand':'tj','no':'1'},{'title':'メフィスト','singer':'Other','brand':'tj','no':'2'}]
        exact,candidates=core.match_track({'title':'メフィスト','artist':'QUEEN BEE'},rows,'2026-10-11')
        self.assertEqual([n['no'] for n in exact],['1']);self.assertEqual([n['no'] for n in candidates],['2'])
