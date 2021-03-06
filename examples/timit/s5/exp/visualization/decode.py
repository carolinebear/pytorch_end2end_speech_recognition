#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Decode the model's outputs (TIMIT corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath
import sys
import argparse
import re

sys.path.append(abspath('../../../'))
from models.load_model import load
from examples.timit.s5.exp.dataset.load_dataset import Dataset
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

MAX_DECODE_LEN_PHONE = 71
MIN_DECODE_LEN_PHONE = 13


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
        data_type='test',
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

    for batch, is_new_epoch in dataset:
        # Decode
        best_hyps, _, perm_idx = model.decode(
            batch['xs'], batch['x_lens'],
            beam_width=args.beam_width,
            max_decode_len=MAX_DECODE_LEN_PHONE,
            min_decode_len=MIN_DECODE_LEN_PHONE,
            length_penalty=args.length_penalty,
            coverage_penalty=args.coverage_penalty)

        if model.model_type == 'attention' and model.ctc_loss_weight > 0:
            best_hyps_ctc, perm_idx = model.decode_ctc(
                batch['xs'], batch['x_lens'],
                beam_width=args.beam_width)

        ys = batch['ys'][perm_idx]
        y_lens = batch['y_lens'][perm_idx]

        for b in range(len(batch['xs'])):
            ##############################
            # Reference
            ##############################
            if dataset.is_test:
                str_ref = ys[b][0]
                # NOTE: transcript is seperated by space(' ')
            else:
                # Convert from list of index to string
                str_ref = dataset.idx2phone(ys[b][: y_lens[b]])

            ##############################
            # Hypothesis
            ##############################
            # Convert from list of index to string
            str_hyp = dataset.idx2phone(best_hyps[b])

            print('----- wav: %s -----' % batch['input_names'][b])
            print('Ref      : %s' % str_ref)
            print('Hyp      : %s' % str_hyp)
            if model.model_type == 'attention' and model.ctc_loss_weight > 0:
                str_hyp_ctc = dataset.idx2phone(best_hyps_ctc[b])
                print('Hyp (CTC): %s' % str_hyp_ctc)

            # Compute PER
            per, _, _, _ = compute_wer(ref=str_ref.split(' '),
                                       hyp=re.sub(r'(.*) >(.*)', r'\1',
                                                  str_hyp).split(' '),
                                       normalize=True)
            print('PER: %.3f %%' % (per * 100))
            if model.model_type == 'attention' and model.ctc_loss_weight > 0:
                per_ctc, _, _, _ = compute_wer(ref=str_ref.split(' '),
                                               hyp=str_hyp_ctc.split(' '),
                                               normalize=True)
                print('PER (CTC): %.3f %%' % (per_ctc * 100))

        if is_new_epoch:
            break


if __name__ == '__main__':
    main()
