import unittest,tempfile,json
from pathlib import Path
import core,song_labels,song_identity
class LabelTests(unittest.TestCase):
 def test_repeated_credit_artist(self):
  self.assertEqual(core.canonical('Kai · Kai · Kai'),'Kai')
  self.assertEqual(core.canonical('Kai · Kai · Kai · Kai'),'Kai')
  self.assertEqual(core.canonical('SEGA SOUND TEAM · Kai · Kai · Kai'),'SEGA SOUND TEAM · Kai')
  self.assertEqual(core.canonical('Kairiki bear · MARETU'),'かいりきベア · MARETU')
  self.assertEqual(core.canonical('kenkaiyosi · kenkaiyosi · kenkaiyosi'),'kenkaiyosi')
  self.assertEqual(core.canonical('星街すいせい · kenkaiyosi · kenkaiyosi'),'星街すいせい · kenkaiyosi')
  self.assertEqual(core.canonical('Ｋａｉ·Kai • kai'),'Kai')
  self.assertEqual(core.canonical('Yorushika ・ ヨルシカ'),'ヨルシカ')
  self.assertEqual(core.canonical('ROSÉ · Bruno Mars'),'ROSÉ · Bruno Mars')
  self.assertEqual(core.canonical('ナナヲアカリ'),'ナナヲアカリ')
 def test_bilingual_and_features(self):
  t={'title':'青春コンプレックス - seisyun complex','artist':'結束バンド'}
  rows=[{'title':'青春コンプレックス','singer':'結束バンド','brand':'joysound','no':'611954'}]
  self.assertEqual(len(core.match_track(t,rows,'2026-10-12')[0]),1)
  t={'title':'マーシャル・マキシマイザー','artist':'柊マグネタイト'}
  rows=[{'title':'マーシャル・マキシマイザー feat.可不(KAFU)','singer':'柊マグネタイト','brand':'dam','no':'7654-64'}]
  self.assertEqual(len(core.match_track(t,rows,'2026-10-12')[0]),1)
 def test_versions_and_different_artist_not_connected(self):
  t={'title':'Song','artist':'Artist'}
  for title,artist in [('Song (Live)','Artist'),('Song','Other')]:
   self.assertEqual(core.match_track(t,[{'title':title,'singer':artist,'brand':'dam','no':'1'}],'2026-10-12')[0],[])
 def test_original_video_bilingual_alias(self):
  labels=song_labels.video_labels({'title':'米津玄師 - アイネクライネ , Kenshi Yonezu - Eine Kleine','channel':'Kenshi Yonezu 米津玄師'},{'title':'Eine Kleine','artist':'米津玄師'})
  self.assertIn('アイネクライネ',[a['title'] for a in labels])
 def test_auto_merge_reversible_and_respects_rejection(self):
  for reject in (False,True):
   with tempfile.TemporaryDirectory() as folder:
    db=core.connect(Path(folder)/'test.db');edits={}
    for vid,title in [('a','昼鳶 - Burglar'),('b','Burglar')]:
     core.save_video(db,{'video_id':vid,'title':title,'channel':'Yorushika - Topic'});db.execute('INSERT INTO events VALUES (?,?,?,?,?)',(vid,vid,'2026-10-01T00:00:00Z','',title));edits[vid]={'title':title,'artist':'ヨルシカ'}
    core.set_state(db,'corrections',edits,'user_state');core.rebuild(db);tracks=core.tracks(db)
    if reject:song_identity.different(db,tracks[0]['id'],tracks[1]['id'])
    result=song_identity.auto_merge(db);self.assertEqual(result['merged'],0 if reject else 1)
    if not reject:
     self.assertEqual(core.tracks(db)[0]['history_records'],2);song_identity.undo(db,result['changes'][0]['id']);self.assertEqual(len(core.tracks(db)),2)
    db.close()

 def test_dual_artist_prefix_not_shared_title(self):
  for title in ['Lemon','IRIS OUT','KICK BACK']:
   labels=song_labels.video_labels({'title':'米津玄師  Kenshi Yonezu - '+title,'channel':'Kenshi Yonezu 米津玄師'},{'title':title,'artist':'米津玄師'})
   self.assertEqual({a['title'] for a in labels},{title})
