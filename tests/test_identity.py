import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core, song_identity, song_search

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=core.connect(Path(self.tmp.name)/'test.sqlite3')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def ingest(self,titles):
        rows=[{'title':title,'titleUrl':'https://www.youtube.com/watch?v='+str(i).zfill(11),'time':'2026-10-10T08:00:00Z','subtitles':[{'name':'Artist - Topic'}]} for i,title in enumerate(titles)]
        core.import_bytes(self.db,json.dumps(rows).encode(),'history.json');core.rebuild(self.db)
    def test_different_song_pair_is_persistent_symmetric_and_reversible(self):
        self.ingest(['Song name','Song names']);a,b=core.tracks(self.db)
        self.assertEqual(len(song_identity.candidates(self.db)),1)
        song_identity.different(self.db,a['id'],b['id']);core.rebuild(self.db)
        self.assertEqual(song_identity.candidates(self.db),[]);self.assertEqual(len(core.tracks(self.db)),2)
        saved=list(core.get_state(self.db,'different_songs',{},'user_state').values())
        self.assertTrue(song_identity.marked_different(b,a,saved))
        song_identity.different(self.db,b['id'],a['id'],restore=True)
        self.assertEqual(len(song_identity.candidates(self.db)),1)

    def test_merge_undo_preserves_records_queue_hidden_and_numbers(self):
        self.ingest(['ラグトレイン','Lagtrain']);items=core.tracks(self.db);a,b=items
        core.set_state(self.db,'queue',[a['id']],'user_state');core.set_state(self.db,'hidden',[a['id']],'user_state')
        number={'brand':'tj','no':'123','source':'manual'}
        core.set_state(self.db,'numbers',{a['id']:[number]},'user_state');self.db.commit()
        change=song_identity.merge(self.db,a['id'],b['id']);merged=core.tracks(self.db)
        self.assertEqual(len(merged),1);self.assertEqual(merged[0]['history_records'],2)
        self.assertTrue(merged[0]['hidden']);self.assertIn(number,merged[0]['numbers']);self.assertEqual(song_identity.queue(self.db),[b['id']])
        song_identity.undo(self.db,change['id']);restored={t['id']:t for t in core.tracks(self.db)}
        self.assertEqual(len(restored),2);self.assertTrue(restored[a['id']]['hidden']);self.assertFalse(restored[b['id']]['hidden'])
        self.assertEqual(song_identity.queue(self.db),[a['id']]);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],2)
    def test_only_presentation_variants_auto_merge(self):
        self.ingest(['Song','Song (Official Music Video)','Song (Live)','Song 2'])
        self.assertEqual(len(core.tracks(self.db)),3)
        self.assertEqual(next(t for t in core.tracks(self.db) if t['title']=='Song')['history_records'],2)
    def test_chain_undo_and_same_track_rejection(self):
        self.ingest(['A','B','C']);a,b,c=core.tracks(self.db)
        with self.assertRaises(ValueError):song_identity.merge(self.db,a['id'],a['id'])
        first=song_identity.merge(self.db,a['id'],b['id']);second=song_identity.merge(self.db,b['id'],c['id'])
        self.assertEqual(core.tracks(self.db)[0]['history_records'],3)
        with self.assertRaises(ValueError):song_identity.undo(self.db,first['id'])
        song_identity.undo(self.db,second['id']);song_identity.undo(self.db,first['id']);self.assertEqual(len(core.tracks(self.db)),3)
    def test_lyric_site_parser_reads_metadata(self):
        document='<tr><td><p class="searchResult__title"><a href="/lyric/abc123/">曲 &amp; Song</a></p></td><td class="searchResult__artist"><a href="/artist/1/">Artist</a></td></tr>'
        self.assertEqual(song_search.parse('utaten',document)[0]['title'],'曲 & Song')
        bugs='<tr><a href="https://music.bugs.co.kr/track/123">info</a><p class="title"><a href="javascript:;">노래</a></p><p class="artist"><a>가수</a></p></tr>'
        self.assertEqual(song_search.parse('bugs',bugs)[0]['url'],'https://music.bugs.co.kr/track/123')
    def test_search_cached_without_network(self):
        import time
        core.set_state(self.db,'song_search_cache',{'bugs|Song|Artist':{'time':time.time(),'result':{'candidates':[]}}},'user_state');self.db.commit()
        self.assertTrue(song_search.search(self.db,'Song','Artist')['cached'])
    def test_shared_performance_suffix_is_not_an_alias(self):
        self.ingest(['Michizure - From THE FIRST TAKE','Stellar Stellar - From THE FIRST TAKE'])
        self.assertFalse(song_identity.candidates(self.db))

if __name__=='__main__':unittest.main()
