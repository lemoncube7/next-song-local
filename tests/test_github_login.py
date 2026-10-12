import unittest,io,time,subprocess
from unittest.mock import patch
import github_sync

class LoginTests(unittest.TestCase):
 def test_code_without_newline_and_explicit_stdin(self):
  class Process:
   stdout=io.StringIO('! First copy your one-time code: ABCD-1234')
   def poll(self):return None
   def wait(self):return 1
   def kill(self):pass
  with patch('github_sync.gh_executable',return_value='gh.exe'),patch('github_sync.subprocess.Popen',return_value=Process()) as run:
   github_sync.start_login()
   for _ in range(100):
    if not github_sync.AUTH_LOCK.locked():break
    time.sleep(.01)
   self.assertEqual(github_sync.AUTH_STATE.get('code'),'ABCD-1234')
   self.assertEqual(run.call_args.kwargs['stdin'],subprocess.DEVNULL)
   self.assertEqual(run.call_args.kwargs['encoding'],'utf-8')
