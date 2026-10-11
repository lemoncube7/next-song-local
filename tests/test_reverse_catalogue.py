import sys,unittest
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import reverse_catalogue

class ReverseTests(unittest.TestCase):
    def test_index_overlapping_and_latin_boundaries(self):
        index=reverse_catalogue.TitleIndex(['he','she','hers'])
        self.assertEqual(index.find('ushers'),{'he','she','hers'})
        rows={'die':[{'title':'Die','singer':'Artist','brand':'tj','no':'1'}]}
        self.assertEqual(reverse_catalogue.match({'title':'Audience','channel':'Artist','category':'Music'},rows,reverse_catalogue.TitleIndex(rows)),[])

    def test_cover_matches_original_artist_and_longest_title(self):
        rows={'song':[{'title':'Song','singer':'Original','brand':'tj','no':'1'}],
              'longsong':[{'title':'Long Song','singer':'Original','brand':'tj','no':'2'}]}
        index=reverse_catalogue.TitleIndex(rows)
        found=reverse_catalogue.match({'title':'Original - Long Song / Cover','channel':'Cover singer','category':'Music'},rows,index)
        self.assertEqual(len(found),1);self.assertEqual(found[0]['title'],'Long Song')
        self.assertEqual(found[0]['artist'],'Original')
        self.assertEqual(reverse_catalogue.match({'title':'Song review','channel':'Talk','category':'Gaming'},rows,index),[])

    def test_title_only_other_singer_and_medley_not_saved(self):
        rows={'song':[{'title':'Song','singer':'Original','brand':'tj','no':'1'}]};index=reverse_catalogue.TitleIndex(rows)
        self.assertEqual(reverse_catalogue.match({'title':'Song','channel':'Other','category':'Music'},rows,index),[])
        self.assertEqual(reverse_catalogue.match({'title':'Original - Song medley','channel':'Original','category':'Music'},rows,index),[])
