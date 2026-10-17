import base64,json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,friends,server,github_sync

CLIENT='a'*32;PEER='b'*32;REPO='owner/private'
def song(title='Song',artist='Artist',**extra):return {'title':title,'artist':artist,'aliases':[],'numbers':[{'brand':'tj','no':'123'}],**extra}
def profile(login='bob',contacts=None,share=True):
    return {'format':friends.FORMAT,'version':1,'client_id':PEER,'login':login,'display_name':'Bob','friends':contacts or [],'share_songs':share,'songs':[song()] if share else []}

class FriendTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=core.connect(Path(self.tmp.name)/'test.sqlite3');friends.ensure(self.db);self.db.commit()
        core.set_state(self.db,'friends_account','alice');self.db.commit()
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def peer(self,doc=None,client=PEER):
        value=doc or profile(contacts=['alice']);value={**value,'client_id':client}
        self.db.execute('INSERT OR REPLACE INTO friend_profiles VALUES (?,?,?,?)',(REPO,'social/'+client+'.json','sha',json.dumps(value)));self.db.commit()
    def test_private_by_default_and_projection(self):
        track=song(id='local',history_records=200,last_watch='secret',video_ids=['abcdefghijk'])
        doc=friends.document(self.db,CLIENT,'alice',[track]);self.assertEqual(doc['songs'],[])
        friends.save_settings(self.db,{'share_songs':True})
        doc=friends.document(self.db,CLIENT,'alice',[track]);encoded=json.dumps(doc)
        for forbidden in ('history_records','last_watch','video_ids','abcdefghijk','secret'):self.assertNotIn(forbidden,encoded)
        self.assertEqual(friends.validate('social/'+CLIENT+'.json',doc),doc)
    def test_username_normalized_and_self_rejected(self):
        self.assertEqual(friends.save_settings(self.db,{'friends':['BoB','bob']})['friends'],['bob'])
        for value in ('alice','https://github.com/bob','a@b.com'):
            with self.assertRaises(ValueError):friends.save_settings(self.db,{'friends':[value]})
    def test_mutual_registration_required(self):
        friends.save_settings(self.db,{'friends':['bob']});self.peer(profile(contacts=['someone']))
        self.assertEqual(friends.status(self.db,REPO)['friends'][0]['state'],'pending')
        with self.assertRaises(ValueError):friends.listing(self.db,REPO,'bob')
        self.peer();self.assertEqual(friends.status(self.db,REPO)['friends'][0]['state'],'accepted')
    def test_incoming_rejection_persists(self):
        self.peer();self.assertEqual(friends.status(self.db,REPO)['friends'][0]['state'],'incoming')
        friends.save_settings(self.db,{'blocked':['bob']});self.assertEqual(friends.status(self.db,REPO)['friends'],[])
        friends.save_settings(self.db,{'friends':['bob']});self.assertEqual(friends.settings(self.db)['blocked'],[])
    def test_private_shelf_hidden_and_repo_isolation(self):
        friends.save_settings(self.db,{'friends':['bob']});self.peer(profile(contacts=['alice'],share=False))
        self.assertEqual(friends.listing(self.db,REPO,'bob')['total'],0)
        self.assertEqual(friends.status(self.db,'other/repo')['friends'][0]['state'],'pending')
    def test_no_history_fields_accepted(self):
        doc=profile();doc['songs'][0]['records']=10
        with self.assertRaises(ValueError):friends.validate('social/'+PEER+'.json',doc)
    def test_match_alias_and_number_without_mutating_tracks(self):
        local=[song('Translated','Artist',id='local',history_records=50,aliases=[{'title':'Original','artist':'Artist'}])]
        other=[song('Original','Artist')]
        before=json.dumps(local)
        result=friends.common(local,other);self.assertEqual(len(result),1);self.assertEqual(result[0]['local_id'],'local')
        self.assertEqual(len(result[0]['common_numbers']),1);self.assertEqual(json.dumps(local),before)
        self.assertEqual(friends.common([song(numbers=[])],[song('Other','Else',numbers=[])]),[])
    def test_multiple_devices_privacy_withdrawal_wins(self):
        friends.save_settings(self.db,{'friends':['bob']});self.peer()
        self.peer(profile(contacts=['alice'],share=False),client='c'*32)
        self.assertEqual(friends.listing(self.db,REPO,'bob')['total'],0)
    def test_sync_publish_receive_and_disable(self):
        friends.save_settings(self.db,{'friends':['bob'],'share_songs':True})
        peer=profile(contacts=['alice']);writes=[]
        def request(path,token,payload=None,missing_ok=False):
            if payload is not None:writes.append(json.loads(base64.b64decode(payload['content'])));return {}
            if path=='/user':return {'login':'alice'}
            if '/git/blobs/' in path:return {'size':500,'content':base64.b64encode(json.dumps(peer).encode()).decode()}
            if '/contents/' in path:return {'sha':'old'}
            raise AssertionError(path)
        args=(self.db,threading.Lock(),{'repo':REPO,'client_id':CLIENT},{'private':True,'default_branch':'main'},
              {'tree':[{'path':'social/'+PEER+'.json','sha':'peer'}]},'fake',request)
        with patch('friends.core.tracks',return_value=[song(history_records=100)]):
            friends.sync(*args)
            friends.save_settings(self.db,{'share_songs':False});friends.sync(*args)
        self.assertEqual(writes[0]['songs'],[song()]);self.assertEqual(writes[1]['songs'],[])
        self.assertEqual(friends.status(self.db,REPO)['friends'][0]['state'],'accepted')
    def test_public_repository_rejected_before_network(self):
        with self.assertRaises(ValueError):friends.sync(self.db,threading.Lock(),{}, {'private':False},{},'fake',lambda *a: self.fail('network'))
    def test_new_user_receives_incoming_without_publishing_shelf(self):
        peer=profile(contacts=['alice'])
        def request(path,token,payload=None,missing_ok=False):
            self.assertIsNone(payload)
            if path=='/user':return {'login':'alice'}
            return {'size':500,'content':base64.b64encode(json.dumps(peer).encode()).decode()}
        friends.sync(self.db,threading.Lock(),{'repo':REPO,'client_id':CLIENT},{'private':True,'default_branch':'main'},
                     {'tree':[{'path':'social/'+PEER+'.json','sha':'peer'}]},'fake',request)
        self.assertEqual(friends.status(self.db,REPO)['friends'][0]['state'],'incoming')
    def test_http_endpoints_and_csrf(self):
        path=Path(self.tmp.name)/'test.sqlite3';original=core.connect
        with patch('server.core.connect',side_effect=lambda:original(path)),patch('server.github_sync.config',return_value={'repo':REPO}),patch('server.github_sync.notify'):
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(http.server_port)
            try:
                request=urllib.request.Request(base+'/api/friends',data=json.dumps({'friends':['bob']}).encode(),headers={'X-App-Token':server.TOKEN,'Content-Type':'application/json'})
                with urllib.request.urlopen(request) as response:self.assertEqual(json.load(response)['friends'],['bob'])
                with urllib.request.urlopen(base+'/api/friends') as response:self.assertEqual(json.load(response)['settings']['friends'],['bob'])
                request=urllib.request.Request(base+'/api/friends',data=b'{}',headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
                self.assertEqual(error.exception.code,403)
            finally:http.shutdown();http.server_close();thread.join()
    def test_repo_owner_credential_without_global_switch(self):
        from types import SimpleNamespace
        with patch('github_sync.gh_executable',return_value='gh'),patch('github_sync.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='fake-token')) as run:
            self.assertEqual(github_sync.credential({'repo':'owner/private'}),'fake-token')
            self.assertEqual(run.call_args.args[0][-2:],['--user','owner'])
        with patch('github_sync.gh_executable',return_value='gh'),patch('github_sync.subprocess.run',side_effect=[SimpleNamespace(returncode=1,stdout=''),SimpleNamespace(returncode=0,stdout='friend-token')]) as run:
            self.assertEqual(github_sync.credential({'repo':'owner/private'}),'friend-token')
            self.assertEqual(run.call_count,2)

if __name__=='__main__':unittest.main()
