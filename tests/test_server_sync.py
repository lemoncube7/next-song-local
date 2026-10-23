import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server_sync
class ServerSyncTest(unittest.TestCase):
 def test_device_token_is_protected_and_not_returned(self):
  with tempfile.TemporaryDirectory() as d,patch.object(server_sync,'path',return_value=Path(d)/'config.json'),patch.object(server_sync.personal_sync,'protect',side_effect=lambda b,decrypt=False:b[::-1]),patch.object(server_sync,'request',return_value={'token':'nsd_secret','code':'1234ABCD','expires':123,'verification_url':server_sync.BASE+'/?pair=1234ABCD'}):
   r=server_sync.begin();self.assertNotIn('token',r);self.assertNotIn('nsd_secret',(Path(d)/'config.json').read_text());self.assertEqual(server_sync.token(server_sync.config()),'nsd_secret')
 def test_no_share_without_opt_in(self):
  with patch.object(server_sync,'config',return_value={'protected_token':'protected'}),patch.object(server_sync,'token',return_value='token'),patch.object(server_sync,'request',return_value={'profile':{'share':0}}) as call:
   with self.assertRaises(ValueError):server_sync.sync(None)
   self.assertEqual(call.call_count,1)
if __name__=='__main__':unittest.main()
