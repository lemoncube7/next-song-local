import unittest
import description_identity as d
class DescriptionIdentityTests(unittest.TestCase):
 def test_explicit_translation_titles(self):
  r=d.identity({'title':'Night Scenery - Inabakumori (English Subbed)','description':'Music: Inabakumori 稲葉曇\nAlternative Titles:\n稲葉曇 「夜間景観」 Vo. 歌愛ユキ\nNight Scenery ; Inabakumori\n'})
  self.assertEqual(r['track']['title'],'夜間景観')
 def test_gaming_music_archive(self):
  r=d.identity({'title':'ECiLA by seibin','channel':'DJMAX ARCHIVE','category':'Gaming','description':'Title: ECiLA\nArtist: seibin\nVocal by Lency'})
  self.assertEqual(r['track']['artist'],'seibin')
  r=d.identity({'title':'Accelerate by Teminite & Skybreak','channel':'DJMAX ARCHIVE','description':'Title: Accelerate\nArtist: Teminite & Skybreak Thanks to Monstercat'})
  self.assertEqual(r['track']['artist'],'Teminite & Skybreak')
  self.assertIsNone(d.identity({'title':'Game review','channel':'Other','category':'Gaming','description':'Title: Background song\nArtist: Artist'}))
 def test_translation_original_link(self):
  original={'classification':{'status':'song','title':'ボルテッカー','artist':'DECO*27'}}
  v={'title':'볼트태클 / DECO*27 / 하츠네 미쿠[자막]','description':'원곡: https://youtu.be/C-7TIDIKc98'}
  self.assertEqual(d.identity(v,lambda _:original)['track']['title'],'ボルテッカー')
  v['title']='다른 제목 cover [자막]'
  self.assertIsNone(d.identity(v,lambda _:original))
 def test_original_without_link(self):
  r=d.identity({'title':'「セプテンバーさん」 cover','description':'Original: セプテンバーさん / RADWIMPS'})
  self.assertEqual(r['track']['artist'],'RADWIMPS')
 def test_artist_first_and_feat(self):
  r=d.identity({'title':'Beyond the way cover','description':'Original: Giga - Beyond the way ft.Miku【MV】'})
  self.assertEqual(r['track']['title'],'Beyond the way')
 def test_unrelated_credit_not_saved(self):
  self.assertIsNone(d.identity({'title':'ゲーム実況','description':'music: Song / Artist'}))
 def test_original_vocal_and_channel_agree(self):
  r=d.identity({'title':'End of days','channel':'배카인','description':'Vocal by 배카인\nComposed by 배카인'})
  self.assertEqual(r['track']['artist'],'배카인')
 def test_cover_vocal_not_used_as_original(self):
  self.assertIsNone(d.identity({'title':'Song cover','channel':'Artist','description':'Vocal by Artist\nComposed by Artist'}))
