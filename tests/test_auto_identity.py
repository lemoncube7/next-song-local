import unittest,tempfile,threading
from pathlib import Path
import core,auto_identity
class GraphTests(unittest.TestCase):
 def test_reference_inference_propagation_cache_and_manual_protection(self):
  with tempfile.TemporaryDirectory() as folder:
   db=core.connect(Path(folder)/'test.db')
   original={'video_id':'abcdefghijk','title':'Song','channel':'Artist - Topic','category':'Music','metadata_status':'ok','classification':{'status':'review'}}
   core.save_video(db,original)
   for i in ['11111111111','22222222222','33333333333']:
    core.save_video(db,{'video_id':i,'title':'Song cover','channel':'Cover singer','category':'Music','description':'Original: https://youtu.be/abcdefghijk','classification':{'status':'review'}})
    db.execute('INSERT INTO events VALUES (?,?,?,?,?)',(i,i,'2026-10-01T00:00:00Z','','Song cover'))
   core.set_state(db,'corrections',{'33333333333':{'exclude':True}},'user_state');db.commit()
   result=auto_identity.run(db,threading.RLock(),0)
   self.assertEqual(result['saved'],2)
   self.assertEqual(result['unique_references'],1)
   self.assertTrue(core.get_state(db,'corrections',{},'user_state')['33333333333']['exclude'])
   self.assertEqual(auto_identity.run(db,threading.RLock(),0)['saved'],0)
   self.assertFalse(any('abcdefghijk' in t['video_ids'] for t in core.tracks(db)))
   db.close()
