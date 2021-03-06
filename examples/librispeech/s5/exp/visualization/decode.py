#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Decode the model's outputs (Librispeech corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath
import sys
import argparse
import re

sys.path.append(abspath('../../../'))
from models.load_model import load
from examples.librispeech.s5.exp.dataset.load_dataset import Dataset
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
                    help='the size of beam')
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
        label_type=params['label_type'],
        batch_size=args.eval_batch_size, splice=params['splice'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        sort_utt=True, reverse=True, tool=params['tool'])

    params['num_classes'] = dataset.num_classes

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

    if dataset.label_type == 'word':
        map_fn = dataset.idx2word
        max_decode_len = MAX_DECODE_LEN_WORD
        min_decode_len = MIN_DECODE_LEN_WORD
    else:
        map_fn = dataset.idx2char
        max_decode_len = MAX_DECODE_LEN_CHAR
        min_decode_len = MIN_DECODE_LEN_CHAR

    for batch, is_new_epoch in dataset:
        # Decode
        best_hyps, _, perm_idx = model.decode(
            batch['xs'], batch['x_lens'],
            beam_width=args.beam_width,
            max_decode_len=max_decode_len,
            min_decode_len=min_decode_len,
            length_penalty=args.length_penalty,
            coverage_penalty=args.coverage_penalty)

        if model.model_type == 'attention' and model.ctc_loss_weight > 0:
            best_hyps_ctc, perm_idx = model.decode_ctc(
                batch['xs'], batch['x_lens'], beam_width=args.beam_width)

        ys = batch['ys'][perm_idx]
        y_lens = batch['y_lens'][perm_idx]

        for b in range(len(batch['xs'])):
            ##############################
            # Reference
            ##############################
            if dataset.is_test:
                str_ref = ys[b][0]
                # NOTE: transcript is seperated by space('_')
            else:
                # Convert from list of index to string
                str_ref = map_fn(ys[b][:y_lens[b]])

            ##############################
            # Hypothesis
            ##############################
            # Convert from list of index to string
            str_hyp = map_fn(best_hyps[b])

            print('----- wav: %s -----' % batch['input_names'][b])
            print('Ref: %s' % str_ref.replace('_', ' '))
            print('Hyp: %s' % str_hyp.replace('_', ' '))
            if model.model_type == 'attention' and model.ctc_loss_weight > 0:
                str_hyp_ctc = map_fn(best_hyps_ctc[b])
                print('Hyp (CTC): %s' % str_hyp_ctc)

            try:
                # Compute WER
                wer, _, _, _ = compute_wer(
                    ref=str_ref.split('_'),
                    hyp=re.sub(r'(.*)[_]*>(.*)', r'\1', str_hyp).split('_'),
                    normalize=True)
                print('WER: %.3f %%' % (wer * 100))
                if model.model_type == 'attention' and model.ctc_loss_weight > 0:
                    wer_ctc, _, _, _ = compute_wer(
                        ref=str_ref.split('_'),
                        hyp=str_hyp_ctc.split('_'),
                        normalize=True)
                    print('WER (CTC): %.3f %%' % (wer_ctc * 100))
            except:
                print('--- skipped ---')

        if is_new_epoch:
            break


if __name__ == '__main__':
    main()
