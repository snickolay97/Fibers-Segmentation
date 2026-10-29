import unittest
from unittest.mock import patch

import cv2
import numpy as np

from src.app_settings import PipelineSettings, PipelineCancelled
from src.block1_preprocessor import GlobalPreprocessor


FILTER_FLAGS = ('enable_bilateral', 'enable_tophat', 'enable_gamma',
                'enable_closing', 'enable_dilation')


class FilterSelectionTests(unittest.TestCase):
    @staticmethod
    def image():
        rng = np.random.RandomState(20261029)
        image = rng.randint(0, 35, size=(96,112)).astype(np.uint8)
        image[20:60,18:30] = 155
        image[32:40,30:80] = 215
        return image

    @staticmethod
    def disabled(**overrides):
        settings = PipelineSettings(**{name:False for name in FILTER_FLAGS})
        for key,value in overrides.items():setattr(settings,key,value)
        return settings.validate()

    def test_all_enabled_matches_previous_pipeline_bit_for_bit(self):
        image = self.image()
        settings = PipelineSettings()
        # Independent reference for the pipeline before filter selection.
        denoised = cv2.bilateralFilter(image,9,45,15)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(171,171))
        top = cv2.morphologyEx(denoised,cv2.MORPH_TOPHAT,kernel)
        top = cv2.normalize(top,None,0,255,cv2.NORM_MINMAX,dtype=cv2.CV_8U)
        lut = np.array([((i/255.)**(1./1.2))*255 for i in range(256)]).astype(np.uint8)
        expected = cv2.LUT(top,lut)
        baseline = GlobalPreprocessor._compute_fast_otsu(expected)
        _,mask = cv2.threshold(expected,max(10,int(baseline*.25)),255,cv2.THRESH_BINARY)
        close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(17,17))
        buffer = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
        expected_mask = cv2.dilate(cv2.morphologyEx(mask,cv2.MORPH_CLOSE,close),buffer,iterations=1)
        filtered,protective = GlobalPreprocessor(settings).process(image)
        np.testing.assert_array_equal(filtered,expected)
        np.testing.assert_array_equal(protective,expected_mask)

    def test_all_disabled_preserves_grayscale_and_still_builds_otsu_mask(self):
        image = np.zeros((64,80),np.uint8)
        image[:,16:24] = 10
        image[:,24:48] = 60
        image[:,48:] = 200
        before = image.copy()
        settings = self.disabled(otsu_safety_factor=.9)
        processor = GlobalPreprocessor(settings)
        self.assertEqual(processor._compute_fast_otsu(image),60)
        with patch.object(processor,'apply_bilateral',side_effect=AssertionError('disabled bilateral ran')), \
             patch.object(processor,'apply_tophat',side_effect=AssertionError('disabled top-hat ran')), \
             patch.object(processor,'apply_gamma',side_effect=AssertionError('disabled gamma ran')), \
             patch('src.block1_preprocessor.cv2.morphologyEx',side_effect=AssertionError('disabled closing ran')), \
             patch('src.block1_preprocessor.cv2.dilate',side_effect=AssertionError('disabled dilation ran')):
            filtered,mask = processor.process(image)
        np.testing.assert_array_equal(filtered,before)
        np.testing.assert_array_equal(image,before)
        np.testing.assert_array_equal(mask,(image>54).astype(np.uint8)*255)

    def test_each_grayscale_step_can_be_enabled_independently(self):
        image = self.image()
        for flag,method in [('enable_bilateral','apply_bilateral'),
                            ('enable_tophat','apply_tophat'),('enable_gamma','apply_gamma')]:
            with self.subTest(flag=flag):
                processor = GlobalPreprocessor(self.disabled(**{flag:True}))
                expected = getattr(processor,method)(image)
                self.assertFalse(np.array_equal(expected,image))
                with patch.object(processor,method,wraps=getattr(processor,method)) as enabled:
                    filtered,mask = processor.process(image)
                enabled.assert_called_once()
                np.testing.assert_array_equal(filtered,expected)
                threshold = max(10,int(processor._compute_fast_otsu(expected)*processor.settings.otsu_safety_factor))
                np.testing.assert_array_equal(mask,(expected>threshold).astype(np.uint8)*255)

    def test_each_protective_morphology_step_can_be_enabled_independently(self):
        image = np.zeros((40,40),np.uint8)
        image[10:30,8:18] = 200
        image[10:30,20:30] = 200
        raw = (image>10).astype(np.uint8)*255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
        cases = [dict(enable_closing=True,bridge_kernel_size=5),
                 dict(enable_dilation=True,buffer_kernel_size=5)]
        for values in cases:
            with self.subTest(values=values):
                expected = (cv2.morphologyEx(raw,cv2.MORPH_CLOSE,kernel) if 'enable_closing' in values
                            else cv2.dilate(raw,kernel,iterations=1))
                self.assertFalse(np.array_equal(expected,raw))
                filtered,mask = GlobalPreprocessor(self.disabled(**values)).process(image)
                np.testing.assert_array_equal(filtered,image)
                np.testing.assert_array_equal(mask,expected)

    def test_skip_progress_is_explicit_monotone_and_includes_thresholding(self):
        events = []
        GlobalPreprocessor(self.disabled(),progress=events.append).process(self.image())
        self.assertEqual({e['operation'] for e in events if e['status']=='skipped'},
                         {'bilateral','tophat','gamma','closing','dilation'})
        self.assertTrue(any(e['operation']=='otsu' and e['status']=='running' for e in events))
        self.assertEqual([e['current'] for e in events],sorted(e['current'] for e in events))
        self.assertTrue(all(e['total']==6 and 0<=e['current']<=6 for e in events))
        self.assertEqual((events[-1]['status'],events[-1]['current']),('completed',6))

    def test_skipped_steps_still_honor_cancellation(self):
        stopped = [False]
        events = []
        def progress(event):
            events.append(event)
            stopped[0] = True
        processor = GlobalPreprocessor(self.disabled(),progress=progress,cancelled=lambda:stopped[0])
        with self.assertRaises(PipelineCancelled):processor.process(self.image())
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['status'],'skipped')

    def test_settings_roundtrip_and_older_dict_enable_all_steps(self):
        settings = self.disabled(enable_gamma=True,enable_dilation=True)
        restored = PipelineSettings.from_dict(settings.to_dict())
        self.assertEqual(restored.to_dict(),settings.to_dict())
        legacy = settings.to_dict()
        for name in FILTER_FLAGS:legacy.pop(name)
        old = PipelineSettings.from_dict(legacy)
        self.assertTrue(all(getattr(old,name) is True for name in FILTER_FLAGS))
        self.assertFalse(any(name in legacy for name in FILTER_FLAGS))

    def test_enable_flags_reject_non_boolean_values(self):
        for flag in FILTER_FLAGS:
            for invalid in (0,1,'false',None):
                with self.subTest(flag=flag,value=invalid):
                    with self.assertRaises(ValueError):PipelineSettings.from_dict({flag:invalid})


if __name__=='__main__':unittest.main()
