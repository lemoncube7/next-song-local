import json, tempfile, unittest
from pathlib import Path
import core, github_sync

class SpotifyImportTests(unittest.TestCase):
    def test_import_privacy_dedup_and_recommendation(self):
        with tempfile.TemporaryDirectory() as folder:
            db=core.connect(Path(folder)/'test.sqlite3')
            try:
                rows=[{'ts':'2026-01-01T00:00:00Z','ms_played':50000,'master_metadata_track_name':'Lemon','master_metadata_album_artist_name':'米津玄師','spotify_track_uri':'spotify:track:1234567890123456789012','username':'PRIVATE_SENTINEL','ip_addr':'PRIVATE_SENTINEL'}, {'ts':'2026-01-02T00:00:00Z','ms_played':5,'episode_name':'Podcast'}]
                result=core.import_bytes(db,json.dumps(rows).encode(),'spotify.json')
                self.assertEqual(result['new_records'],1)
                self.assertEqual(result['skipped_records'],1)
                self.assertNotIn('PRIVATE_SENTINEL',''.join(r[0] for r in db.execute('select data from videos')))
                core.rebuild(db)
                self.assertEqual(core.tracks(db)[0]['title'],'Lemon')
                self.assertEqual(github_sync.export_records(db),[])
                self.assertEqual(core.import_bytes(db,json.dumps(rows).encode(),'again.json')['new_records'],0)
                legacy=[{'endTime':'2026-01-01 00:00','msPlayed':50000,'trackName':'Lemon','artistName':'米津玄師'}]
                self.assertEqual(core.import_bytes(db,json.dumps(legacy).encode(),'legacy.json')['new_records'],0)
            finally:db.close()
