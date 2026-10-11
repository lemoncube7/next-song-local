import sys,json,base64,hashlib,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,github_sync
from test_app import history

class FakeGitHub:
    def __init__(self,private=True):self.private=private;self.files={};self.puts=[]
    def request(self,path,token,payload=None,missing_ok=False):
        if path=='/repos/owner/shared':return {'private':self.private,'default_branch':'main'}
        if '/git/trees/' in path:return {'tree':[{'path':p,'sha':hashlib.sha1(v).hexdigest()} for p,v in self.files.items()]}
        if '/git/blobs/' in path:
            sha=path.rsplit('/',1)[1];value=next(v for v in self.files.values() if hashlib.sha1(v).hexdigest()==sha)
            return {'content':base64.b64encode(value).decode(),'size':len(value)}
        filename=path.split('/contents/',1)[1]
        if payload is not None:
            if filename in self.files:assert payload['sha']==hashlib.sha1(self.files[filename]).hexdigest()
            self.files[filename]=base64.b64decode(payload['content']);self.puts.append(filename);return {}
        return {'sha':hashlib.sha1(self.files[filename]).hexdigest()} if filename in self.files else None

class SharingTests(unittest.TestCase):
    def setup_db(self,folder,name,rows,corrections):
        db=core.connect(Path(folder)/(name+'.sqlite3'));core.import_bytes(db,json.dumps(rows).encode(),'private-history.json')
        core.set_state(db,'corrections',corrections,'user_state');core.rebuild(db);return db
    def sync(self,db,client,remote):
        with patch('github_sync.config',return_value={'repo':'owner/shared','token':'SECRET_TOKEN','client_id':client,'enabled':True}),patch('github_sync.request',side_effect=remote.request):return github_sync.sync(db,threading.Lock())

    def test_two_clients_share_identities_without_history_and_apply_before_external_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            a='aaaaaaaaaaa';b='bbbbbbbbbbb';remote=FakeGitHub()
            alice=self.setup_db(folder,'alice',[history(a,title='PRIVATE_ORIGINAL_HISTORY',channel='Private uploader')],{a:{'title':'Confirmed Song','artist':'Artist'}})
            bob=self.setup_db(folder,'bob',[history(a,title='FRIEND_PRIVATE_HISTORY',channel='Other uploader'),history(b,title='Private friend history',channel='Other')],{b:{'title':'한국 노래','artist':'한국 가수'}})
            self.sync(alice,'a'*32,remote);self.sync(bob,'b'*32,remote)
            shared=core.video_data(bob,a)['classification'];self.assertEqual(shared['source'],'shared');self.assertEqual(shared['title'],'Confirmed Song')
            self.sync(alice,'a'*32,remote)
            core.import_bytes(alice,json.dumps([history(b,title='Another private title',channel='Unknown')]).encode(),'more.json');core.rebuild(alice)
            self.assertEqual(core.video_data(alice,b)['classification']['source'],'shared')
            serialized=''.join(v.decode() for v in remote.files.values())
            for forbidden in ['PRIVATE_ORIGINAL_HISTORY','FRIEND_PRIVATE_HISTORY','2026-10-10','SECRET_TOKEN','history_records','events','description']:self.assertNotIn(forbidden,serialized)
            bob_records=[r for p,v in remote.files.items() if '/'+('b'*32)+'/' in p for r in json.loads(v)['records']]
            self.assertEqual([r['video_id'] for r in bob_records],[b])
            calls=len(remote.puts);self.sync(alice,'a'*32,remote);self.assertEqual(len(remote.puts),calls)
            self.assertEqual(alice.execute('SELECT COUNT(*) FROM events').fetchone()[0],2);alice.close();bob.close()

    def test_conflicting_peer_and_local_exclusion_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            vid='aaaaaaaaaaa';remote=FakeGitHub()
            a=self.setup_db(folder,'a',[history(vid,title='Private',channel='Other')],{vid:{'title':'Song A','artist':'Artist A'}})
            b=self.setup_db(folder,'b',[history(vid,title='Private',channel='Other')],{vid:{'title':'Song B','artist':'Artist B'}})
            self.sync(a,'a'*32,remote);self.sync(b,'b'*32,remote);self.sync(a,'a'*32,remote)
            self.assertEqual(a.execute('SELECT COUNT(*) FROM shared_conflicts').fetchone()[0],1)
            self.assertEqual(core.video_data(a,vid)['classification']['title'],'Song A')
            core.set_state(b,'corrections',{vid:{'exclude':True}},'user_state');core.rebuild(b)
            self.sync(b,'b'*32,remote);self.assertEqual(core.video_data(b,vid)['classification']['status'],'excluded');a.close();b.close()

    def test_public_repo_and_unexpected_private_fields_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db=core.connect(Path(folder)/'db.sqlite3');remote=FakeGitHub(private=False)
            with self.assertRaises(ValueError):self.sync(db,'a'*32,remote)
            self.assertEqual(remote.puts,[]);db.close()
        bad={'video_id':'aaaaaaaaaaa','title':'Song','artist':'Artist','aliases':[],'numbers':[],'evidence':'manual','watch_count':5}
        with self.assertRaises(ValueError):github_sync.validate_record(bad)

    def test_verified_aliases_are_not_a_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            db=core.connect(Path(folder)/'db.sqlite3')
            a={'video_id':'aaaaaaaaaaa','title':'日本語曲','artist':'Artist','aliases':[{'title':'English Title','artist':'Artist'}],'numbers':[],'evidence':'manual'}
            b={**a,'title':'English Title','aliases':[],'evidence':'verified_auto'}
            for path,r in [('a',a),('b',b)]:db.execute('INSERT INTO shared_records VALUES (?,?,?)',(path,r['video_id'],json.dumps(r)))
            db.commit();result=github_sync.apply_shared(db,threading.Lock())
            self.assertEqual(result['conflicts'],0);self.assertEqual(result['shared_identities'],1);db.close()
