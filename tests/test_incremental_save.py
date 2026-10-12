import unittest,tempfile,json
from pathlib import Path
import core

class IncrementalSaveTests(unittest.TestCase):
 def test_save_merge_exclude_reset_matches_full_rebuild(self):
  with tempfile.TemporaryDirectory() as folder:
   db=core.connect(Path(folder)/'test.sqlite3')
   for vid in ['a','b']:
    core.save_video(db,{'video_id':vid,'title':'unidentified','metadata_status':'pending'})
    db.execute('INSERT INTO events VALUES (?,?,?,?,?)',(vid,vid,'2026-10-01T00:00:00Z','', 'unidentified'))
   core.rebuild(db)
   edits={}
   for vid,value in [('a',{'title':'Test','artist':'Artist'}),('b',{'title':'Test','artist':'Artist'}),('a',{'exclude':True}),('b',None)]:
    if value is None:edits.pop(vid,None)
    else:edits[vid]=value
    core.set_state(db,'corrections',edits,'user_state');core.rebuild(db,affected_video=vid)
    before={r['id']:json.loads(r['data']) for r in db.execute('SELECT * FROM tracks')}
    counts=core.get_state(db,'classification_counts')
    core.rebuild(db)
    after={r['id']:json.loads(r['data']) for r in db.execute('SELECT * FROM tracks')}
    self.assertEqual(before,after);self.assertEqual(counts,core.get_state(db,'classification_counts'))
   db.close()
