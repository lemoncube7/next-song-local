import sys,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,song_databases

class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=core.connect(Path(self.tmp.name)/'db.sqlite3')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def respond(self,db,provider,path,params,lock):
        if provider=='iTunes':return {'provider':provider,'status':'ok','data':{'results':[
            {'kind':'song','trackName':'フューチャー・イヴ (feat. 初音ミク)','artistName':'sasakure.UK','trackViewUrl':'https://music.apple.com/jp/album/example/1'},
            {'kind':'song','trackName':'フューチャー・イヴ (feat. 初音ミク)','artistName':'sasakure.UK','trackViewUrl':'https://music.apple.com/jp/album/example/2'},
            {'kind':'song','trackName':'フューチャー・イヴ','artistName':'Other','trackViewUrl':'https://music.apple.com/jp/album/example/3'}]}}
        return {'provider':provider,'status':'unavailable','data':None}
    def test_native_title_confirmed_with_card_artist_and_duplicate_releases_collapsed(self):
        video={'video_id':'abcdefghijk','title':'『フューチャー・イヴ』feat.初音ミク','music_metadata':{'cards':[{'title':'FUTURE EVE','artist':'sasakure.UK'}]}}
        with patch('song_databases.request',side_effect=self.respond):result=song_databases.search(self.db,video,threading.Lock())
        self.assertEqual(result['status'],'recognized');self.assertEqual(result['track']['title'],'フューチャー・イヴ')
        self.assertIn({'title':'FUTURE EVE','artist':'sasakure.UK'},result['track']['alternate_labels'])
        self.assertEqual(len(result['candidates']),1)
    def test_cover_and_unrelated_artist_are_never_automatically_confirmed(self):
        for title,artist in [('フューチャー・イヴ cover','sasakure.UK'),('フューチャー・イヴ','Unrelated')]:
            v={'video_id':'abcdefghijk','title':title,'music_metadata':{'cards':[{'title':'FUTURE EVE','artist':artist}]}}
            with patch('song_databases.request',side_effect=self.respond):result=song_databases.search(self.db,v,threading.Lock())
            self.assertNotEqual(result['status'],'recognized')
    def test_vocadb_exact_video_link_is_required_for_automatic_confirmation(self):
        song={'id':1,'name':'Romaji','songType':'Original','names':[{'language':'Japanese','value':'原題'}],'artistString':'Producer','pvs':[{'service':'Youtube','pvId':'abcdefghijk'}]}
        self.assertTrue(song_databases.voca_candidate(song,'abcdefghijk')['confident'])
        self.assertFalse(song_databases.voca_candidate(song,'12345678901')['confident'])
    def test_cache_skips_network_and_failure_is_not_empty_search_success(self):
        params={'term':'a'};key='song_db|iTunes|search|'+json.dumps(params,sort_keys=True,ensure_ascii=False)
        from datetime import datetime,timezone
        saved={'provider':'iTunes','status':'ok','data':{'results':[]},'checked_at':datetime.now(timezone.utc).isoformat()}
        self.db.execute('INSERT INTO queries VALUES (?,?)',(key,json.dumps(saved)));self.db.commit()
        with patch('song_databases.urllib.request.urlopen') as network:
            self.assertTrue(song_databases.request(self.db,'iTunes','search',params,threading.Lock())['cached']);network.assert_not_called()

if __name__=='__main__':unittest.main()
