import json,tempfile,threading,unittest
from pathlib import Path
import core,github_sync,shared_knowledge
from test_github_sync import SharingTests,FakeGitHub
from test_app import history

class KnowledgeTests(SharingTests):
 def test_rejection_protects_against_reapply(self):
  with tempfile.TemporaryDirectory() as folder:
   vid='aaaaaaaaaaa';db=self.setup_db(folder,'a',[history(vid,title='Unknown',channel='Uploader')],{})
   row={'video_id':vid,'title':'Shared Song','artist':'Artist','aliases':[],'numbers':[],'evidence':'manual'}
   db.execute('INSERT INTO shared_records VALUES (?,?,?)',('old',vid,json.dumps(row)))
   github_sync.apply_shared(db,threading.RLock());self.assertEqual(core.video_data(db,vid)['classification']['source'],'shared')
   core.set_state(db,'shared_rejections',{vid:True},'user_state');core.rebuild(db)
   github_sync.apply_shared(db,threading.RLock());self.assertNotEqual(core.video_data(db,vid)['classification'].get('source'),'shared')
   core.set_state(db,'shared_rejections',{},'user_state');core.rebuild(db);self.assertEqual(core.video_data(db,vid)['classification']['source'],'shared');db.close()
 def test_different_video_original_alias_and_withdrawal(self):
  with tempfile.TemporaryDirectory() as folder:
   origin='aaaaaaaaaaa';cover='bbbbbbbbbbb';alias='ccccccccccc';remote=FakeGitHub()
   alice=self.setup_db(folder,'a',[history(origin,title='Native Song',channel='Artist - Topic')],{origin:{'title':'日本語曲','artist':'Artist','alternate_labels':[{'title':'English Song','artist':'Artist'}]}})
   v=core.video_data(alice,origin);v['classification']['source']='topic';core.save_video(alice,v)
   # Export uses the native Topic source for an explicit original anchor.
   self.sync(alice,'a'*32,remote)
   bob=self.setup_db(folder,'b',[history(cover,title='日本語曲 cover',channel='Singer'),history(alias,title='Artist - English Song',channel='Artist')],{})
   v=core.video_data(bob,cover);v.update(title='日本語曲 cover',description='Original: https://youtu.be/'+origin);core.save_video(bob,v)
   self.sync(bob,'b'*32,remote)
   self.assertEqual(core.video_data(bob,cover)['classification']['shared_basis'],'original_link')
   self.assertEqual(core.video_data(bob,alias)['classification']['shared_basis'],'title_artist_alias')
   self.assertEqual(bob.execute('SELECT COUNT(*) FROM events').fetchone()[0],2)
   self.assertFalse(any(origin in t['video_ids'] for t in core.tracks(bob)))
   core.set_state(alice,'corrections',{origin:{'exclude':True}},'user_state');core.rebuild(alice)
   self.sync(alice,'a'*32,remote);result=self.sync(bob,'b'*32,remote)
   self.assertEqual(result['withdrawn_connections'],2)
   self.assertNotEqual(core.video_data(bob,cover)['classification'].get('source'),'shared')
   alice.close();bob.close()
 def test_graph_validation_roles_numbers_and_rejection(self):
  with tempfile.TemporaryDirectory() as folder:
   vid='aaaaaaaaaaa';db=self.setup_db(folder,'a',[history(vid,title='Song cover',channel='Singer')],{vid:{'title':'Song','artist':'Author','original_video_id':'bbbbbbbbbbb'}})
   v=core.video_data(db,vid);v.update(title='Song cover',description='Vocal: Singer');core.save_video(db,v)
   docs=shared_knowledge.documents(db,github_sync.export_records(db),'a'*32)
   for path,doc in docs.items():shared_knowledge.validate(path,doc)
   mapping=next(r for d in docs.values() for r in d['mappings'])
   self.assertEqual((mapping['kind'],mapping['performer']),('cover','Singer'))
   path,doc=next((p,d) for p,d in docs.items() if d['songs'])
   doc['songs'][0]['watch_count']=20
   with self.assertRaises(ValueError):shared_knowledge.validate(path,doc)
   db.close()
