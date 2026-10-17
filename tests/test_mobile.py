import base64,json,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,mobile_transfer as mobile,personal_sync as relay

def track(tid='song',members=None):return {'id':tid,'title':'Song','artist':'Artist','aliases':[],'numbers':[{'brand':'tj','no':'123'}],
    'history_records':10,'last_watch':'2026-10-01T00:00:00Z','base_score':.5,'frequency_score':.3,
    'member_ids':members or [tid],'video_ids':['abcdefghijk'],'source':'private','followed':False,'hidden':False,'karaoke_good':False,'karaoke_rating':0}
def op(kind='rating',target='song',value=1,n=1):return {'id':f'{n:032x}','kind':kind,'target':target,'value':value}

class MobileTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=core.connect(self.root/'db.sqlite3')
    self.patch=patch('core.tracks',return_value=[track(),track('other')]);self.patch.start()
    self.sid=mobile.source_id(self.db)
 def tearDown(self):self.patch.stop();self.db.close();self.tmp.cleanup()
 def payload(self,ops):return {'format':mobile.OPERATIONS,'version':1,'source_id':self.sid,'device_id':'f'*32,'operations':ops}
 def test_snapshot_whitelist_and_source_stable(self):
    doc=mobile.snapshot(self.db);self.assertEqual(doc['source_id'],mobile.source_id(self.db))
    text=json.dumps(doc)
    for forbidden in ('video_ids','abcdefghijk','description','youtube-api-key','gemini-key'):self.assertNotIn(forbidden,text)
    self.assertEqual(doc['tracks'][0]['history_records'],10)
 def test_rating_idempotent(self):
    first=mobile.apply(self.db,self.payload([op()]));again=mobile.apply(self.db,self.payload([op()]))
    self.assertEqual(first['applied'],1);self.assertEqual(again['duplicates'],1)
    self.assertEqual(core.get_state(self.db,'karaoke_ratings',{},'user_state'),{'song':1})
 def test_queue_merge_preserves_pc_changes(self):
    core.set_state(self.db,'queue',['song','other'],'user_state');self.db.commit()
    mobile.apply(self.db,self.payload([op('queue','song',False)]))
    self.assertEqual(core.get_state(self.db,'queue',[],'user_state'),['other'])
 def test_wrong_source_and_unknown_fields_rejected(self):
    bad=self.payload([op()]);bad['source_id']='a'*32
    with self.assertRaises(ValueError):mobile.apply(self.db,bad)
    with self.assertRaises(ValueError):mobile.apply(self.db,{**self.payload([op()]),'token':'private'})
    with self.assertRaises(ValueError):mobile.apply(self.db,self.payload([{**op(),'description':'private'}]))
 def test_missing_track_not_acknowledged(self):
    result=mobile.apply(self.db,self.payload([op(target='missing')]))
    self.assertEqual(result['applied'],0);self.assertEqual(len(result['unresolved']),1)
    self.assertEqual(mobile.snapshot(self.db)['acknowledged_operations'],[])
 def test_merged_song_id_resolved(self):
    with patch('core.tracks',return_value=[track('new',['song','new'])]):mobile.apply(self.db,self.payload([op()]))
    self.assertEqual(core.get_state(self.db,'karaoke_ratings',{},'user_state'),{'new':1})
 def test_failure_rolls_back_entire_batch(self):
    core.set_state(self.db,'friends_account','self');self.db.commit()
    with self.assertRaises(ValueError):mobile.apply(self.db,self.payload([op('follow','Artist',True),op('friend','self',True,2)]))
    self.assertEqual(core.get_state(self.db,'follows',[],'user_state'),[])
    self.assertEqual(mobile.snapshot(self.db)['acknowledged_operations'],[])
 def test_encryption_roundtrip_and_wrong_password(self):
    doc={'format':'next-song-personal','version':1,'snapshot':mobile.snapshot(self.db),'operations':[op()]}
    encrypted=relay.seal(doc,'only-for-tests-password');self.assertNotIn('Song',json.dumps(encrypted))
    self.assertEqual(relay.open_envelope(encrypted,'only-for-tests-password')[0],doc)
    with self.assertRaises(ValueError):relay.open_envelope(encrypted,'wrong-password')
    encrypted['ciphertext']=encrypted['ciphertext'][:-3]+'AAAA'
    with self.assertRaises(ValueError):relay.open_envelope(encrypted,'only-for-tests-password')
 def test_windows_protected_secret(self):
    secret=b'test-only-not-a-real-key';protected=relay.protect(secret)
    self.assertNotIn(secret,protected);self.assertEqual(relay.protect(protected,decrypt=True),secret)
 def test_cloud_conflict_retry_does_not_double_apply(self):
    conf={'enabled':True,'repo':'owner/private','vault':self.sid,'protected_password':base64.b64encode(b'fake-protected').decode()}
    snapshot=mobile.snapshot(self.db);remote={'format':'next-song-personal','version':1,'snapshot':snapshot,'operations':[op()]};calls=[]
    def request(path,token,payload=None,missing_ok=False):
        if path=='/repos/owner/private':return {'private':True,'default_branch':'main'}
        if payload:
            calls.append(payload)
            if len(calls)==1:raise ValueError('GitHub HTTP 409')
            decoded=relay.open_envelope(json.loads(base64.b64decode(payload['content'])),'test-password')[0]
            self.assertEqual(decoded['operations'],[]);return {}
        return {'sha':'revision','size':600,'content':base64.b64encode(json.dumps(relay.seal(remote,'test-password')).encode()).decode()}
    with patch('personal_sync.config',return_value=conf),patch('personal_sync.protect',return_value=b'test-password'),patch('personal_sync.github_sync.credential',return_value='fake-token'),patch('personal_sync.github_sync.request',side_effect=request):relay.run(self.db,threading.Lock())
    self.assertEqual(len(calls),2);self.assertEqual(core.get_state(self.db,'karaoke_ratings',{},'user_state'),{'song':1})

if __name__=='__main__':unittest.main()
