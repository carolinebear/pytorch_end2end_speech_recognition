#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Evaluate the trained hierarchical model (Librispeech corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath
import sys
import argparse

sys.path.append(abspath('../../../'))
from models.load_model import load
from examples.librispeech.s5.exp.dataset.load_dataset_hierarchical import Dataset
from examples.wsj.s5.exp.metrics.character import eval_char
from examples.wsj.s5.exp.metrics.word import eval_word
from utils.config import load_config
from utils.evaluation.logging import set_logger

parser = argparse.ArgumentParser()
parser.add_argument('--data_save_path', type=str,
                    help='path to saved data')
parser.add_argument('--model_path', type=str,
                    help='path to the model to evaluate')
parser.add_argument('--epoch', type=int, default=-1,
                    help='the epoch to restore')
parser.add_argument('--beam_width', type=int, default=1,
                    help='the size of beam in the main task')
parser.add_argument('--beam_width_sub', type=int, default=1,
                    help='the size of beam in the sub task')
parser.add_argument('--eval_batch_size', type=int, default=1,
                    help='the size of mini-batch in evaluation')
parser.add_argument('--length_penalty', type=float, default=0,
                    help='length penalty in beam search decoding')
parser.add_argument('--coverage_penalty', type=float, default=0,
                    help='coverage penalty in beam search decoding')

MAX_DECODE_LEN_WORD = 200
MIN_DECODE_LEN_WORD = 0
MAX_DECODE_LEN_CHAR = 600
MIN_DECODE_LEN_CHAR = 0


def main():

    a2c_oracle = False
    resolving_unk = False

    args = parser.parse_args()

    # Load a config file (.yml)
    params = load_config(join(args.model_path, 'config.yml'), is_eval=True)

    # Setting for logging
    logger = set_logger(args.model_path)

    for i, data_type in enumerate(['dev_clean', 'dev_other', 'test_clean', 'test_other']):
        # Load dataset
        dataset = Dataset(
            data_save_path=args.data_save_path,
            backend=params['backend'],
            input_freq=params['input_freq'],
            use_delta=params['use_delta'],
            use_double_delta=params['use_double_delta'],
            data_type=data_type,
            data_size=params['data_size'],
            label_type=params['label_type'], label_type_sub=params['label_type_sub'],
            batch_size=args.eval_batch_size, splice=params['splice'],
            num_stack=params['num_stack'], num_skip=params['num_skip'],
            sort_utt=False, tool=params['tool'])

        if i == 0:
            params['num_classes'] = dataset.num_classes
            params['num_classes_sub'] = dataset.num_classes_sub

            # Load model
            model = load(model_type=params['model_type'],
                         params=params,
                         backend=params['backend'])

            # Restore the saved parameters
            epoch, _, _, _ = model.load_checkpoint(
                save_path=args.model_path, epoch=args.epoch)

            # GPU setting
            model.set_cuda(deterministic=False, benchmark=True)

            logger.info('beam width (main): %d' % args.beam_width)
            logger.info('beam width (sub) : %d' % args.beam_width_sub)
            logger.info('epoch: %d' % (epoch - 1))
            logger.info('a2c oracle: %s' % str(a2c_oracle))
            logger.info('resolving_unk: %s' % str(resolving_unk))

        wer, df = eval_word(
            models=[model],
            dataset=dataset,
            eval_batch_size=args.eval_batch_size,
            beam_width=args.beam_width,
            max_decode_len=MAX_DECODE_LEN_WORD,
            min_decode_len=MIN_DECODE_LEN_WORD,
            beam_width_sub=args.beam_width_sub,
            max_decode_len_sub=MAX_DECODE_LEN_CHAR,
            min_decode_len_sub=MIN_DECODE_LEN_CHAR,
            length_penalty=args.length_penalty,
            coverage_penalty=args.coverage_penalty,
            progressbar=True,
            resolving_unk=resolving_unk,
            a2c_oracle=a2c_oracle)
        logger.info('  WER (%s, main): %.3f %%' %
                    (dataset.data_type, (wer * 100)))
        logger.info(df)

        wer_sub, cer_sub, df_sub = eval_char(
            models=[model],
            dataset=dataset,
            eval_batch_size=args.eval_batch_size,
            beam_width=args.beam_width_sub,
            max_decode_len=MAX_DECODE_LEN_CHAR,
            min_decode_len=MIN_DECODE_LEN_CHAR,
            length_penalty=args.length_penalty,
            coverage_penalty=args.coverage_penalty,
            progressbar=True)
        logger.info(' WER / CER (%s, sub): %.3f / %.3f %%' %
                    (dataset.data_type, (wer_sub * 100), (cer_sub * 100)))
        logger.info(df_sub)


if __name__ == '__main__':
    main()
