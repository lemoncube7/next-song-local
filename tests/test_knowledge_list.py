import unittest,json,tempfile
from pathlib import Path
import core,knowledge_list
class KnowledgeListTests(unittest.TestCase):
 def test_unwatched_peer_song_search_and_no_history_mutation(self):
  with tempfile.TemporaryDirectory() as d:
   db=core.connect(Path(d)/'test.db')
   core.save_video(db,{'video_id':'aaaaaaaaaaa','title':'Mine','channel':'Artist - Topic'})
   db.execute('INSERT INTO events VALUES (?,?,?,?,?)',('1','aaaaaaaaaaa','2026-10-01T00:00:00Z','','Mine'));core.rebuild(db)
   peer={'video_id':'bbbbbbbbbbb','title':'Peer Song','artist':'Other','aliases':[{'title':'別名','artist':'Other'}],'numbers':[],'evidence':'manual'}
   db.execute('INSERT INTO shared_records VALUES (?,?,?)',('peer',peer['video_id'],json.dumps(peer)));db.commit()
   r=knowledge_list.page(db,scope='unwatched')
   self.assertEqual(r['total'],1);self.assertEqual(r['items'][0]['title'],'Peer Song')
   self.assertEqual(knowledge_list.page(db,query='別名')['total'],1)
   self.assertEqual(knowledge_list.page(db,scope='watched')['total'],1)
   self.assertEqual(len(core.tracks(db)),1);self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
   conflict={**peer,'video_id':'aaaaaaaaaaa','title':'Conflicting peer song'}
   db.execute('INSERT INTO shared_records VALUES (?,?,?)',('peer2',conflict['video_id'],json.dumps(conflict)))
   self.assertEqual(knowledge_list.page(db,query='Conflicting')['items'][0]['history_records'],0)
   db.close()
