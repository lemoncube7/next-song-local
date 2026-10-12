import unittest,sqlite3,json
import video_index

class BrowseIndexTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.executescript('CREATE TABLE videos(id TEXT PRIMARY KEY,data TEXT); CREATE TABLE events(key TEXT PRIMARY KEY,video_id TEXT,time TEXT);')
  self.db.execute('INSERT INTO videos VALUES (?,?)',('a',json.dumps({'video_id':'a','title':'Test Song','classification':{'status':'review'},'video_kind':{'kind':'song'}})))
  self.db.execute("INSERT INTO events VALUES ('1','a','2026-10-01T00:00:00Z')")
  self.db.commit();video_index.ensure(self.db)
 def tearDown(self):self.db.close()
 def test_migration_and_filter(self):
  r=video_index.page(self.db,kind='song',search='test');self.assertEqual(r['total'],1);self.assertEqual(r['items'][0]['history_records'],1)
  self.assertEqual(video_index.page(self.db,kind='activity')['total'],0)
 def test_saves_and_history_stay_synchronized(self):
  self.db.execute("INSERT INTO events VALUES ('2','a','2026-10-02T00:00:00Z')")
  self.assertEqual(video_index.page(self.db)['items'][0]['history_records'],2)
  self.db.execute("DELETE FROM events WHERE key='2'")
  self.assertEqual(video_index.page(self.db)['items'][0]['history_records'],1)
  self.db.execute('INSERT OR REPLACE INTO videos VALUES (?,?)',('a',json.dumps({'video_id':'a','classification':{'status':'excluded'}})))
  self.assertEqual(video_index.page(self.db)['total'],0)
  self.assertEqual(video_index.page(self.db,status='excluded')['total'],1)
 def test_registered_not_in_review(self):
  self.db.execute('UPDATE videos SET data=? WHERE id=?',(json.dumps({'video_id':'a','classification':{'status':'song'}}),'a'))
  self.assertEqual(video_index.page(self.db,status='all')['total'],0)
