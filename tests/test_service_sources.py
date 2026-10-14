import io,json,tempfile,unittest
from pathlib import Path
import core,takeout_html

class ServiceSourcesTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.db=core.connect(Path(self.folder.name)/'db.sqlite3')
    def tearDown(self):self.db.close();self.folder.cleanup()
    def test_spotify_preserves_details_and_recordings(self):
        rows=[]
        for n,uri in enumerate(('1234567890123456789012','2234567890123456789012')):
            rows.append({'ts':f'2026-01-0{n+1}T00:00:00Z','ms_played':12000+n,'skipped':bool(n),'master_metadata_track_name':'Song','master_metadata_album_artist_name':'Artist','master_metadata_album_album_name':'Album '+str(n),'spotify_track_uri':'spotify:track:'+uri,'ip_addr':'SECRET'})
        core.import_bytes(self.db,json.dumps(rows).encode(),'history.json');core.rebuild(self.db)
        track=core.tracks(self.db)[0];d=track['listening_details']['spotify']
        self.assertEqual(d['played_ms'],24001);self.assertEqual(d['skipped_records'],1);self.assertEqual(d['skip_known_records'],2)
        self.assertEqual(len(track['recordings']),2);self.assertEqual(track['recordings'][0]['album'],'Album 0')
        self.assertNotIn('SECRET',''.join(r[0] for r in self.db.execute('select data from event_details')))
        legacy=[{'endTime':'2026-01-01 00:00','msPlayed':12000,'trackName':'Song','artistName':'Artist'}]
        self.assertEqual(core.import_bytes(self.db,json.dumps(legacy).encode(),'legacy.json')['new_records'],0)
        details=json.loads(self.db.execute('select data from event_details order by key').fetchone()[0])
        self.assertIn('track_uri',details)
    def test_youtube_music_source_not_blind_song_identity(self):
        row={'time':'2026-01-01T00:00:00Z','title':'Unknown episode','titleUrl':'https://www.youtube.com/watch?v=ABCDEFGHIJK','header':'YouTube Music','products':['YouTube']}
        core.import_bytes(self.db,json.dumps([row]).encode(),'history.json');core.rebuild(self.db)
        v=core.video_data(self.db,'ABCDEFGHIJK');self.assertTrue(v['music_service_origin']);self.assertEqual(v['classification']['status'],'review')
        v.update(title='Song',channel='Artist - Topic');core.save_video(self.db,v);core.rebuild(self.db)
        self.assertEqual(core.tracks(self.db)[0]['listening_details']['youtube_music']['records'],1)
        row.pop('header');core.import_bytes(self.db,json.dumps([row]).encode(),'again.json')
        self.assertEqual(json.loads(self.db.execute('select data from event_details').fetchone()[0])['platform'],'youtube_music')
    def test_html_header_preserved(self):
        html='''<div class="outer-cell"><div class="header-cell"><p>YouTube Music<br></p></div><div class="content-cell mdl-cell--6-col"><a href="https://music.youtube.com/watch?v=ABCDEFGHIJK">Song</a>을(를) 시청했습니다.<br>2026. 1. 1. 오전 9:00:00 KST</div></div>'''
        rows=list(takeout_html.iter_rows(io.BytesIO(html.encode())))
        self.assertEqual(rows[0]['products'],['YouTube Music'])
