import json,sys,unittest,tempfile,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,music_metadata,recognition

class MusicTests(unittest.TestCase):
    def page(self,header='음악'):
        data={'horizontalCardListRenderer':{'header':{'richListHeaderRenderer':{'title':{'simpleText':header}}},'cards':[{'videoAttributeViewModel':{'title':'白ゆき','subtitle':'n-buna'}}]}}
        return 'var ytInitialData = '+json.dumps(data)+';'
    def test_cards_require_music_heading(self):
        self.assertEqual(music_metadata.extract(self.page())[0]['title'],'白ゆき')
        self.assertEqual(music_metadata.extract(self.page('추천')),[])
    def test_vocal_suffix_is_alias_not_song_title(self):
        result=music_metadata.identity({'video_id':'abcdefghijk','title':'オーバーコード / 初音ミク','music_metadata':{'cards':[{'title':'オーバーコード / 初音ミク','artist':'いえぬ'}]}})
        self.assertEqual(result['track']['title'],'オーバーコード')
        self.assertEqual(result['track']['alternate_labels'][0]['title'],'オーバーコード / 初音ミク')
    def test_cover_credit_without_cover_keyword_is_not_confirmed(self):
        video={'video_id':'abcdefghijk','title':'キラーチューン / ラプラス・ダークネス-東京事変','music_metadata':{'cards':[{'title':'キラーチューン _ ラプラス・ダークネス-東京事変','artist':'ラプラス・ダークネス'}]}}
        self.assertTrue(music_metadata.risky_video(video))
        self.assertEqual(music_metadata.identity(video)['status'],'ambiguous')
        self.assertEqual(music_metadata.identity(video)['candidates'][0]['artist'],'東京事変')
    def test_cover_and_multiple_cards_need_confirmation(self):
        v={'video_id':'abcdefghijk','title':'白ゆき cover','music_metadata':{'cards':[{'title':'白ゆき','artist':'n-buna'}]}}
        self.assertEqual(music_metadata.identity(v)['status'],'ambiguous')
        v['title']='白ゆき';v['music_metadata']['cards']*=2
        self.assertEqual(music_metadata.identity(v)['status'],'ambiguous')
    def test_native_title_from_reference_preserves_roman_alias(self):
        v={'video_id':'abcdefghijk','title':'とても素敵な六月でした [가사]','music_metadata':{'cards':[{'title':'Totemo Sutekina Rokugatsu Deshita','artist':'Eight','video_id':'12345678901'}]}}
        result=music_metadata.identity(v,lambda _: {'classification':{'status':'song','title':'とても素敵な六月でした','artist':'Eight'}})
        self.assertEqual(result['status'],'recognized');self.assertEqual(result['track']['title'],'とても素敵な六月でした')
        self.assertEqual(result['track']['alternate_labels'][0]['title'],'Totemo Sutekina Rokugatsu Deshita')
    def test_fetch_cache_preserves_existing_video_and_does_not_create_events(self):
        with tempfile.TemporaryDirectory() as folder:
            db=core.connect(Path(folder)/'test.sqlite3');v={'video_id':'abcdefghijk','title':'User title'};core.save_video(db,v);db.commit()
            with patch('pipeline.fetch',return_value=self.page()) as fetch:
                music_metadata.ensure(db,v,threading.Lock());fresh=core.video_data(db,v['video_id'])
                music_metadata.ensure(db,fresh,threading.Lock());self.assertEqual(fetch.call_count,1)
            self.assertEqual(fresh['title'],'User title');self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],0);db.close()

if __name__=='__main__':unittest.main()
