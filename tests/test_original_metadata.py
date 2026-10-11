import json, sys, tempfile, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core, original_metadata, recognition

ORIGINAL='12345678901'
COVER={'video_id':'abcdefghijk','title':'Song Cover','channel':'Singer','description':'Original: https://youtu.be/'+ORIGINAL}
ITEM={'id':ORIGINAL,'snippet':{'title':'Artist - Song','channelTitle':'Artist','description':'Music : Artist','categoryId':'10'}}

class OriginalMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=core.connect(Path(self.tmp.name)/'db.sqlite3')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_fetch_cache_and_never_create_watch_history(self):
        with patch('original_metadata.request_videos',return_value={'status':'ok','items':[ITEM]}) as request:
            r=original_metadata.ensure_originals(self.db,COVER,'test-key')
            self.assertEqual(r['fetched'],1);request.assert_called_once_with([ORIGINAL],'test-key')
            self.assertEqual(original_metadata.ensure_originals(self.db,COVER,'test-key')['status'],'cached')
            self.assertEqual(request.call_count,1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)
        core.rebuild(self.db);self.assertEqual(core.tracks(self.db),[])
        r=recognition.recognize(COVER,lookup=lambda vid:core.video_data(self.db,vid))
        self.assertEqual(r['status'],'recognized');self.assertEqual(r['track']['artist'],'Artist')
    def test_no_key_and_http_failure_do_not_discard_candidates(self):
        with patch('original_metadata.request_videos') as request:
            self.assertEqual(original_metadata.ensure_originals(self.db,COVER,'')['status'],'no_key');request.assert_not_called()
        with patch('original_metadata.request_videos',return_value={'status':'failed','reason':'YouTube API HTTP 403'}) as request:
            self.assertEqual(original_metadata.ensure_originals(self.db,COVER,'test-key')['status'],'failed')
            self.assertEqual(original_metadata.ensure_originals(self.db,COVER,'test-key')['status'],'failed');self.assertEqual(request.call_count,1)
        self.assertIsNone(core.video_data(self.db,ORIGINAL))
    def test_deleted_original_is_negative_cached(self):
        with patch('original_metadata.request_videos',return_value={'status':'ok','items':[]}) as request:
            self.assertEqual(original_metadata.ensure_originals(self.db,COVER,'test-key')['unavailable'],[ORIGINAL])
            original_metadata.ensure_originals(self.db,COVER,'test-key');self.assertEqual(request.call_count,1)
    def test_concurrent_clicks_share_cached_fetch(self):
        import concurrent.futures
        dbpath=Path(self.tmp.name)/'db.sqlite3'
        def fetch():
            db=core.connect(dbpath)
            try:return original_metadata.ensure_originals(db,COVER,'test-key')
            finally:db.close()
        with patch('original_metadata.request_videos',return_value={'status':'ok','items':[ITEM]}) as request:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:fetch(),range(2)))
            self.assertEqual(request.call_count,1)
    def test_key_not_in_url_or_error_text(self):
        error=urllib.error.HTTPError('secret-url',403,'Forbidden',{},None)
        with patch('original_metadata.urllib.request.urlopen',side_effect=error) as request:
            result=original_metadata.request_videos([ORIGINAL],'test-secret-key')
            self.assertNotIn('test-secret-key',json.dumps(result));self.assertNotIn('test-secret-key',request.call_args.args[0].full_url)

if __name__=='__main__':unittest.main()
