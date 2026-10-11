import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import google_search
class GoogleTests(unittest.TestCase):
    def test_search_metadata_and_original_result_link(self):
        doc='<a href="https://open.spotify.com/track/example"><h3>フラジール ‑ 曲・歌詞：ぬゆり</h3></a>'
        items,candidates=google_search.parse(doc)
        self.assertEqual(items[0]['title'],'フラジール ‑ 曲・歌詞：ぬゆり')
        self.assertEqual(candidates[0]['title'],'フラジール');self.assertEqual(candidates[0]['artist'],'ぬゆり')
    def test_non_music_results_are_not_song_candidates(self):
        items,candidates=google_search.parse('<a href="https://example.com"><h3>Some unrelated tutorial</h3></a>')
        self.assertEqual(len(items),1);self.assertFalse(candidates)
    def test_english_song_metadata(self):
        _,candidates=google_search.parse('<a href="/url?q=https://open.spotify.com/track/example"><h3>Song - song and lyrics by Artist | Spotify</h3></a>')
        self.assertEqual(candidates[0]['artist'],'Artist')
if __name__=='__main__':unittest.main()
