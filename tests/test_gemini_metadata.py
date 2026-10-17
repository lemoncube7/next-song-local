import io,json,sqlite3,sys,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gemini_metadata as gm

class FakeTime:
    def __init__(self):self.now=1780000000.;self.waits=[]
    def clock(self):return self.now
    def sleep(self,seconds):self.waits.append(seconds);self.now+=seconds

class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.fake=FakeTime()
        self.client=gm.Client(self.root,clock=self.fake.clock,sleeper=self.fake.sleep)
        (self.root/'data/gemini-key.txt').write_text('test-key',encoding='utf8')
    def tearDown(self):self.tmp.cleanup()
    def test_restart_preserves_spacing(self):
        a=self.client.reserve(100);self.client.finish(a,200,100)
        second=gm.Client(self.root,clock=self.fake.clock,sleeper=self.fake.sleep)
        second.reserve(100)
        self.assertGreaterEqual(sum(self.fake.waits),15)
    def test_parallel_lease_and_tpm(self):
        self.client.reserve(9000)
        other=gm.Client(self.root,clock=self.fake.clock,sleeper=self.fake.sleep)
        other.reserve(2000)
        self.assertGreaterEqual(sum(self.fake.waits),120)
    def test_tpm_window_separate_from_rpm(self):
        a=self.client.reserve(8000);self.client.finish(a,200,8000)
        self.client.reserve(3000)
        self.assertGreaterEqual(sum(self.fake.waits),60)
    def test_daily_cap_stops_without_sleep(self):
        self.client.settings['rpd']=1
        a=self.client.reserve(100);self.client.finish(a,200)
        with self.assertRaises(gm.Deferred):self.client.reserve(100)
        self.assertEqual(self.fake.waits,[])
    def test_server_retry_delay_and_daily(self):
        body=json.dumps({'error':{'details':[{'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'90s'},
             {'@type':'type.googleapis.com/google.rpc.QuotaFailure','violations':[{'quotaId':'GenerateRequestsPerDay','quotaValue':'20'}]}]}})
        info=gm.retry_details(429,{'Retry-After':'120'},body,0,self.fake.now)
        self.assertEqual(info['delay'],121);self.assertTrue(info['daily'])
    def test_observed_limits_are_persistent(self):
        self.client.learn_limits([{'quotaId':'GenerateRequestsPerMinute','quotaValue':'2'}])
        other=gm.Client(self.root,clock=self.fake.clock,sleeper=self.fake.sleep)
        self.assertEqual(other.settings['rpm'],1)
    def test_non_song_has_no_identity_and_fabricated_quote_rejected(self):
        a={'kind':'A',**{k:None for k in gm.FIELDS},'song_title':'Song','original_artist':'Artist','evidence':['Original: Song / Artist']}
        self.assertTrue(gm.validate({'title':'Song cover','description':'Original: Song / Artist'},a)['identity_grounded'])
        self.assertFalse(gm.validate({'title':'Song cover','description':''},a)['identity_grounded'])
        with self.assertRaises(ValueError):gm.validate({'title':'','description':''},{**a,'kind':'C'})
    def test_minimized_input_omits_secrets_and_history(self):
        v={'title':'Song','description':'Original: Artist\nmail: a@b.com\n계좌후원 : 123-456-78900\nhttps://site/path?token=secret',
           'watch_time':'private','account':'private'}
        serialized=json.dumps(gm.metadata(v))
        for text in ('private','a@b.com','123-456','token=secret'):self.assertNotIn(text,serialized)
    def test_503_retry_and_cache_share_limiter(self):
        answer={'kind':'A',**{k:None for k in gm.FIELDS},'song_title':'Song','original_artist':'Artist','evidence':['Song / Artist']}
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(answer)}]}}],
                  'usageMetadata':{'promptTokenCount':100}}
        self.client.open=Mock(side_effect=[urllib.error.HTTPError('https://example.invalid',503,'busy',{},io.BytesIO(b'{}')),
                                         io.BytesIO(json.dumps(response).encode())])
        first=self.client.extract({'title':'Song / Artist'})
        second=self.client.extract({'title':'Song / Artist'})
        self.assertTrue(first['identity_grounded']);self.assertTrue(second['cached'])
        self.assertEqual(self.client.open.call_count,2);self.assertGreaterEqual(sum(self.fake.waits),31)
    def test_daily_error_does_not_loop(self):
        body=json.dumps({'error':{'status':'RESOURCE_EXHAUSTED','details':[{'@type':'google.rpc.QuotaFailure',
            'violations':[{'quotaId':'RequestsPerDay','quotaValue':'50'}]}]}}).encode()
        self.client.open=Mock(side_effect=urllib.error.HTTPError('https://example.invalid',429,'daily',{},io.BytesIO(body)))
        with self.assertRaises(gm.Deferred):self.client.extract({'title':'Song / Artist'})
        self.assertEqual(self.client.open.call_count,1)
    def test_network_retry_waits_and_preserves_attempt(self):
        answer={'kind':'C',**{k:None for k in gm.FIELDS},'evidence':['gameplay']}
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(answer)}]}}],
                  'usageMetadata':{'promptTokenCount':100}}
        self.client.open=Mock(side_effect=[urllib.error.URLError(ConnectionResetError()),io.BytesIO(json.dumps(response).encode())])
        result=self.client.extract({'title':'gameplay'})
        self.assertEqual(result['answer']['kind'],'C');self.assertGreaterEqual(sum(self.fake.waits),60)
        with self.client.db() as db:
            self.assertEqual(db.execute('SELECT status FROM gemini_attempts ORDER BY id').fetchall(),[('network_error',),('200',)])
    def test_daily_timezone_dst(self):
        # USA DST transition days can be shorter/longer than 24 hours.
        import datetime
        for stamp in ('2026-03-08T12:00:00+00:00','2026-11-01T12:00:00+00:00'):
            now=datetime.datetime.fromisoformat(stamp).timestamp()
            start,end=gm.day_window(now)
            self.assertLessEqual(start,now);self.assertGreater(end,now)
    def test_permanent_auth_error_not_retried(self):
        self.client.open=Mock(side_effect=urllib.error.HTTPError('https://example.invalid',403,'denied',{},io.BytesIO(b'{}')))
        with self.assertRaises(gm.Deferred):self.client.extract({'title':'Song'})
        self.assertEqual(self.client.open.call_count,1)

if __name__=='__main__':unittest.main()
