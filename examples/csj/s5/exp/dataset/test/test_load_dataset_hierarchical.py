#! /usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import sys
import unittest

sys.path.append(os.path.abspath('../../../../../../'))
from examples.csj.s5.exp.dataset.load_dataset_hierarchical import Dataset
from utils.measure_time_func import measure_time


class TestLoadDatasetHierarchical(unittest.TestCase):

    def test(self):

        # data_type
        # self.check(label_type='word', label_type_sub='character_wb',
        #            data_type='train')
        self.check(label_type='word', label_type_sub='character_wb',
                   data_type='dev')
        self.check(label_type='word', label_type_sub='character_wb',
                   data_type='eval1')
        self.check(label_type='word', label_type_sub='character_wb',
                   data_type='eval2')
        self.check(label_type='word', label_type_sub='character_wb',
                   data_type='eval3')

        # label_type
        # self.check(label_type='word', label_type_sub='phone_wb')
        # self.check(label_type='character_wb', label_type_sub='phone_wb')
        # self.check(label_type='character', label_type_sub='phone')

    @measure_time
    def check(self, label_type, label_type_sub, data_type='dev',
              data_size='all', backend='pytorch',
              shuffle=False, sort_utt=True, sort_stop_epoch=None,
              frame_stacking=False, splice=1, num_gpus=1):

        print('========================================')
        print('  backend: %s' % backend)
        print('  label_type: %s' % label_type)
        print('  label_type_sub: %s' % label_type_sub)
        print('  data_type: %s' % data_type)
        print('  data_size: %s' % data_size)
        print('  shuffle: %s' % str(shuffle))
        print('  sort_utt: %s' % str(sort_utt))
        print('  sort_stop_epoch: %s' % str(sort_stop_epoch))
        print('  frame_stacking: %s' % str(frame_stacking))
        print('  splice: %d' % splice)
        print('  num_gpus: %d' % num_gpus)
        print('========================================')

        num_stack = 3 if frame_stacking else 1
        num_skip = 3 if frame_stacking else 1
        dataset = Dataset(
            data_save_path='/n/sd8/inaguma/corpus/csj/kaldi',
            backend=backend,
            input_freq=81, use_delta=True, use_double_delta=True,
            data_type=data_type, data_size=data_size,
            label_type=label_type, label_type_sub=label_type_sub,
            batch_size=64, max_epoch=1, splice=splice,
            num_stack=num_stack, num_skip=num_skip,
            min_frame_num=40, shuffle=shuffle,
            sort_utt=sort_utt, reverse=True, sort_stop_epoch=sort_stop_epoch,
            num_gpus=num_gpus, tool='htk', num_enque=None)

        print('=> Loading mini-batch...')
        map_fn = dataset.idx2word
        map_fn_sub = dataset.idx2char

        for batch, is_new_epoch in dataset:
            if data_type == 'train' and backend == 'pytorch':
                for i in range(len(batch['xs'])):
                    if batch['xs'].shape[1] < batch['ys'].shape[1]:
                        raise ValueError(
                            'input length must be longer than label length.')

            if dataset.is_test:
                str_true = batch['ys'][0][0]
                str_true_sub = batch['ys_sub'][0][0]
            else:
                str_true = map_fn(batch['ys'][0][:batch['y_lens'][0]])
                str_true_sub = map_fn_sub(
                    batch['ys_sub'][0][:batch['y_lens_sub'][0]])

            print('----- %s (epoch: %.3f, batch: %d) -----' %
                  (batch['input_names'][0], dataset.epoch_detail, len(batch['xs'])))
            print('=' * 20)
            print(str_true)
            print('-' * 10)
            print(str_true_sub)
            print('x_lens: %d' % (batch['x_lens'][0] * num_stack))
            if not dataset.is_test:
                print('y_lens (word): %d' % batch['y_lens'].data[0])
                print('y_lens_sub (char): %d' %
                      batch['y_lens_sub'].data[0])

            if dataset.epoch_detail >= 0.1:
                break


if __name__ == '__main__':
    unittest.main()
