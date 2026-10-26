"""Optional regressions against visually annotated local photographs.

The photographs remain in ignored data/. These bounds check known failures;
they are not an accuracy estimate for the entire library.
"""
import json
import unittest
from pathlib import Path

import numpy as np

from imaging import automatic_process, artwork_aspect, effective_crop_points


ROOT=Path(__file__).resolve().parent
PROJECT=ROOT/'data'/'project.json'


@unittest.skipUnless(PROJECT.exists(),'Local photograph fixtures are unavailable')
class PhotographRegressions(unittest.TestCase):
    def test_022_same_colour_backing_is_not_part_of_fan_sheet(self):
        items=json.loads(PROJECT.read_text('utf-8'))
        item=next(x for x in items if x['name'].startswith('会员_022_'))
        result=automatic_process(ROOT/'data'/'originals'/item['file'],0,artwork_aspect(item['name'],item['width'],item['height']))
        points=np.asarray(result['points'])
        self.assertEqual(result['auto_result']['method'],'same-colour-sheet')
        self.assertTrue(np.all((points[:2,1]>.05)&(points[:2,1]<.075)),points)
        self.assertTrue(np.all((points[2:,1]>.74)&(points[2:,1]<.765)),points)
        self.assertLess(points[0,0],.002);self.assertGreater(points[1,0],.998)

    def test_bottom_character_and_faint_upper_seal_survive(self):
        items=json.loads(PROJECT.read_text('utf-8'))
        for number in ('069','135'):
            with self.subTest(artwork=number):
                item=next(x for x in items if x['name'].startswith('会员_'+number+'_'))
                result=automatic_process(ROOT/'data'/'originals'/item['file'],0,artwork_aspect(item['name'],item['width'],item['height']))
                p=np.asarray(effective_crop_points(result['points'],item['width'],item['height'],result['trim']))
                if number=='069':
                    self.assertGreater(min(p[2:,1]),.943,'keep the last stroke of 身 and its lower margin')
                else:
                    y=448/4031
                    right=p[1,0]+(p[2,0]-p[1,0])*(y-p[1,1])/(p[2,1]-p[1,1])
                    self.assertGreater(right*3023,1940,'keep the complete pale red seal')

    def test_008_top_edge_does_not_follow_slanted_backing(self):
        items=json.loads(PROJECT.read_text('utf-8'))
        item=next(x for x in items if x['name'].startswith('会员_008_'))
        result=automatic_process(ROOT/'data'/'originals'/item['file'],0,artwork_aspect(item['name'],item['width'],item['height']))
        top=np.asarray(result['points'])[:2,1]*4031
        # Original photograph: paper starts near y=38 on the left and y=32
        # on the right, rather than at the photograph's upper-right boundary.
        self.assertTrue(np.all((top>26)&(top<46)),top)
        self.assertLess(abs(top[0]-top[1]),12)

    def test_final_crop_keeps_reported_seal_and_top_strokes(self):
        items=json.loads(PROJECT.read_text('utf-8'))
        for number in ('004','032'):
            with self.subTest(artwork=number):
                item=next(x for x in items if x['name'].startswith('会员_'+number+'_'))
                result=automatic_process(ROOT/'data'/'originals'/item['file'],0,artwork_aspect(item['name'],item['width'],item['height']))
                outline=np.asarray(effective_crop_points(result['points'],item['width'],item['height'],result['trim']))
                if number=='004':
                    self.assertGreater(outline[1,0],.81,'right seal must remain inside final export')
                    self.assertLess(outline[0,0],.165,'left strokes must remain inside final export')
                else:
                    self.assertLess(max(outline[:2,1]),.017,'top crossing strokes must remain inside final export')

    def test_reported_failures_keep_the_complete_paper(self):
        items=json.loads(PROJECT.read_text('utf-8'))
        # Normalized corners read independently from the original photographs.
        expected={
            '002':[[.357,.033],[.651,.033],[.653,.953],[.343,.953]],
            '020':[[.284,.012],[.600,.012],[.592,.969],[.268,.969]],
            '073':[[.430,.045],[.722,.041],[.713,.952],[.444,.949]],
            '079':[[.376,.047],[.641,.046],[.641,.952],[.370,.952]],
            '082':[[.428,.062],[.709,.061],[.708,.987],[.415,.984]],
            '129':[[.462,.043],[.670,.040],[.658,.956],[.451,.954]],
        }
        for number,points in expected.items():
            with self.subTest(artwork=number):
                item=next(x for x in items if x['name'].startswith('会员_'+number+'_'))
                result=automatic_process(ROOT/'data'/'originals'/item['file'],item['rotation'],artwork_aspect(item['name'],item['width'],item['height'],item['rotation']))
                self.assertLess(np.max(np.abs(np.asarray(result['points'])-points)),.013)

    def test_incorrect_catalogue_aspect_does_not_cut_wide_work(self):
        items=json.loads(PROJECT.read_text('utf-8'))
        for number in ('077','085'):
            with self.subTest(artwork=number):
                item=next(x for x in items if x['name'].startswith('会员_'+number+'_'))
                result=automatic_process(ROOT/'data'/'originals'/item['file'],item['rotation'],artwork_aspect(item['name'],item['width'],item['height'],item['rotation']))
                points=np.asarray(result['points'])
                self.assertGreater(np.ptp(points[:,0]),.55)
                self.assertGreater(np.ptp(points[:,1]),.85)


if __name__=='__main__':
    unittest.main(verbosity=2)
