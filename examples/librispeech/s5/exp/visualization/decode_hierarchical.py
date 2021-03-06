#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Decode the hierarchical model's outputs (Librispeech corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath
import sys
import argparse
import re

sys.path.append(abspath('../../../'))
from models.load_model import load
from examples.librispeech.s5.exp.dataset.load_dataset_hierarchical import Dataset
from utils.config import load_config
from utils.evaluation.edit_distance import compute_wer

parser = argparse.ArgumentParser()
parser.add_argument('--data_save_path', type=str,
                    help='path to saved data')
parser.add_argument('--model_path', type=str,
                    help='path to the model to evaluate')
parser.add_argument('--epoch', type=int, default=-1,
                    help='the epoch to restore')
parser.add_argument('--eval_batch_size', type=int, default=1,
                    help='the size of mini-batch in evaluation')
parser.add_argument('--beam_width', type=int, default=1,
                    help='the size of beam in the main task')
parser.add_argument('--beam_width_sub', type=int, default=1,
                    help='the size of beam in the sub task')
parser.add_argument('--length_penalty', type=float, default=0,
                    help='length penalty in beam search decoding')
parser.add_argument('--coverage_penalty', type=float, default=0,
                    help='coverage penalty in beam search decoding')

MAX_DECODE_LEN_WORD = 200
MIN_DECODE_LEN_WORD = 0
MAX_DECODE_LEN_CHAR = 600
MIN_DECODE_LEN_CHAR = 0


def main():

    args = parser.parse_args()

    # Load a config file (.yml)
    params = load_config(join(args.model_path, 'config.yml'), is_eval=True)

    # Load dataset
    dataset = Dataset(
        data_save_path=args.data_save_path,
        backend=params['backend'],
        input_freq=params['input_freq'],
        use_delta=params['use_delta'],
        use_double_delta=params['use_double_delta'],
        data_type='test_clean',
        # data_type='test_other',
        data_size=params['data_size'],
        label_type=params['label_type'], label_type_sub=params['label_type_sub'],
        batch_size=args.eval_batch_size, splice=params['splice'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        sort_utt=True, reverse=True, tool=params['tool'])

    params['num_classes'] = dataset.num_classes
    params['num_classes_sub'] = dataset.num_classes_sub

    # Load model
    model = load(model_type=params['model_type'],
                 params=params,
                 backend=params['backend'])

    # Restore the saved parameters
    model.load_checkpoint(save_path=args.model_path, epoch=args.epoch)

    # GPU setting
    model.set_cuda(deterministic=False, benchmark=True)

    # sys.stdout = open(join(model.model_dir, 'decode.txt'), 'w')

    ######################################################################

    for batch, is_new_epoch in dataset:
        # Decode
        best_hyps, aw, perm_idx = model.decode(
            batch['xs'], batch['x_lens'],
            beam_width=args.beam_width,
            max_decode_len=MAX_DECODE_LEN_WORD,
            min_decode_len=MIN_DECODE_LEN_WORD,
            length_penalty=args.length_penalty,
            coverage_penalty=args.coverage_penalty)
        best_hyps_sub, aw_sub, _ = model.decode(
            batch['xs'], batch['x_lens'],
            beam_width=args.beam_width_sub,
            max_decode_len=MAX_DECODE_LEN_CHAR,
            min_decode_len=MIN_DECODE_LEN_CHAR,
            length_penalty=args.length_penalty,
            coverage_penalty=args.coverage_penalty,
            task_index=1)

        ys = batch['ys'][perm_idx]
        y_lens = batch['y_lens'][perm_idx]
        ys_sub = batch['ys_sub'][perm_idx]
        y_lens_sub = batch['y_lens_sub'][perm_idx]

        for b in range(len(batch['xs'])):
            ##############################
            # Reference
            ##############################
            if dataset.is_test:
                str_ref = ys[b][0]
                str_ref_sub = ys_sub[b][0]
                # NOTE: transcript is seperated by space('_')
            else:
                # Convert from list of index to string
                str_ref = dataset.idx2word(ys[b][: y_lens[b]])
                str_ref_sub = dataset.idx2char(ys_sub[b][:y_lens_sub[b]])

            ##############################
            # Hypothesis
            ##############################
            # Convert from list of index to string
            str_hyp = dataset.idx2word(best_hyps[b])
            str_hyp_sub = dataset.idx2char(best_hyps_sub[b])

            ##############################
            # Resolving UNK
            ##############################
            if 'OOV' in str_hyp and resolving_unk:
                str_hyp_no_unk = resolve_unk(
                    str_hyp, best_hyps_sub[b], aw[b], aw_sub[b], dataset.idx2char)

            print('----- wav: %s -----' % batch['input_names'][b])
            print('Ref         : %s' % str_ref.replace('_', ' '))
            print('Hyp (main)  : %s' % str_hyp.replace('_', ' '))
            print('Hyp (sub)   : %s' % str_hyp_sub.replace('_', ' '))
            if 'OOV' in str_hyp and resolving_unk:
                print('Hyp (no UNK): %s' % str_hyp_no_unk.replace('_', ' '))

            try:
                wer, _, _, _ = compute_wer(
                    ref=str_ref.split('_'),
                    hyp=re.sub(r'(.*)_>(.*)', r'\1', str_hyp).split('_'),
                    normalize=True)
                print('WER (main)  : %.3f %%' % (wer * 100))
                wer_sub, _, _, _ = compute_wer(
                    ref=str_ref_sub.split('_'),
                    hyp=re.sub(r'(.*)>(.*)', r'\1',
                               str_hyp_sub).split('_'),
                    normalize=True)
                print('WER (sub)  : %.3f %%' % (wer_sub * 100))
                if 'OOV' in str_hyp and resolving_unk:
                    wer_no_unk, _, _, _ = compute_wer(
                        ref=str_ref.split('_'),
                        hyp=re.sub(r'(.*)_>(.*)', r'\1',
                                   str_hyp_no_unk.replace('*', '')).split('_'),
                        normalize=True)
                    print('WER (no UNK): %.3f %%' % (wer_no_unk * 100))
            except:
                print('--- skipped ---')

        if is_new_epoch:
            break


if __name__ == '__main__':
    main()
