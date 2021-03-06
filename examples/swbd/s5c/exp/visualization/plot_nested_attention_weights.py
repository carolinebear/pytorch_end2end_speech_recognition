#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Plot attention weights of the nested attention model (Switchboard corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath, isdir
import sys
import argparse
import shutil
import numpy as np

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
plt.style.use('ggplot')
import seaborn as sns
sns.set_style("white")
blue = '#4682B4'
orange = '#D2691E'
green = '#006400'

# sns.set(font='IPAMincho')
sns.set(font='Noto Sans CJK JP')

sys.path.append(abspath('../../../'))
from models.load_model import load
from examples.swbd.s5c.exp.dataset.load_dataset_hierarchical import Dataset
from utils.io.labels.character import Idx2char
from utils.io.labels.word import Idx2word
from utils.directory import mkdir_join, mkdir
from utils.visualization.attention import plot_hierarchical_attention_weights
from utils.config import load_config

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
parser.add_argument('--length_penalty', type=float,
                    help='length penalty in beam search decodding')


MAX_DECODE_LEN_WORD = 100
MAX_DECODE_LEN_CHAR = 300


def main():

    args = parser.parse_args()

    # Load a config file (.yml)
    params = load_config(join(args.model_path, 'config.yml'), is_eval=True)

    # Load dataset
    test_data = Dataset(
        data_save_path=args.data_save_path,
        backend=params['backend'],
        input_freq=params['input_freq'],
        use_delta=params['use_delta'],
        use_double_delta=params['use_double_delta'],
        data_type='eval2000_swbd',
        # data_type='eval2000_ch',
        data_size=params['data_size'],
        label_type=params['label_type'], label_type_sub=params['label_type_sub'],
        batch_size=args.eval_batch_size, splice=params['splice'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        sort_utt=False, reverse=False, tool=params['tool'])

    params['num_classes'] = test_data.num_classes
    params['num_classes_sub'] = test_data.num_classes_sub

    # Load model
    model = load(model_type=params['model_type'],
                 params=params,
                 backend=params['backend'])

    # Restore the saved parameters
    model.load_checkpoint(save_path=args.model_path, epoch=args.epoch)

    # GPU setting
    model.set_cuda(deterministic=False, benchmark=True)

    a2c_oracle = False

    # Visualize
    plot(model=model,
         dataset=test_data,
         eval_batch_size=args.eval_batch_size,
         beam_width=args.beam_width,
         beam_width_sub=args.beam_width_sub,
         length_penalty=args.length_penalty,
         a2c_oracle=a2c_oracle,
         save_path=mkdir_join(args.model_path, 'att_weights'))


def plot(model, dataset, eval_batch_size, beam_width, beam_width_sub,
         length_penalty, a2c_oracle=False, save_path=None):
    """Visualize attention weights of Attetnion-based model.
    Args:
        model: model to evaluate
        dataset: An instance of a `Dataset` class
        eval_batch_size (int, optional): the batch size when evaluating the model
        beam_width: (int): the size of beam i nteh main task
        beam_width_sub: (int): the size of beam in the sub task
        length_penalty (float):
        a2c_oracle (bool, optional):
        save_path (string, optional): path to save attention weights plotting
    """
    # Clean directory
    if save_path is not None and isdir(save_path):
        shutil.rmtree(save_path)
        mkdir(save_path)

    idx2word = Idx2word(dataset.vocab_file_path, return_list=True)
    idx2char = Idx2char(dataset.vocab_file_path_sub, return_list=True)

    for batch, is_new_epoch in dataset:

        batch_size = len(batch['xs'])

        if a2c_oracle:
            if dataset.is_test:
                max_label_num = 0
                for b in range(batch_size):
                    if max_label_num < len(list(batch['ys_sub'][b][0])):
                        max_label_num = len(
                            list(batch['ys_sub'][b][0]))

                ys_sub = np.zeros(
                    (batch_size, max_label_num), dtype=np.int32)
                ys_sub -= 1  # pad with -1
                y_lens_sub = np.zeros((batch_size,), dtype=np.int32)
                for b in range(batch_size):
                    indices = char2idx(batch['ys_sub'][b][0])
                    ys_sub[b, :len(indices)] = indices
                    y_lens_sub[b] = len(indices)
                    # NOTE: transcript is seperated by space('_')
            else:
                ys_sub = batch['ys_sub']
                y_lens_sub = batch['y_lens_sub']
        else:
            ys_sub = None
            y_lens_sub = None

        best_hyps, aw, best_hyps_sub, aw_sub, aw_dec, _ = model.decode(
            batch['xs'], batch['x_lens'],
            beam_width=beam_width,
            beam_width_sub=beam_width_sub,
            max_decode_len=MAX_DECODE_LEN_WORD,
            max_decode_len_sub=MAX_DECODE_LEN_CHAR,
            length_penalty=length_penalty,
            teacher_forcing=a2c_oracle,
            ys_sub=ys_sub,
            y_lens_sub=y_lens_sub)

        for b in range(batch_size):
            word_list = idx2word(best_hyps[b])
            char_list = idx2char(best_hyps_sub[b])

            speaker = '_'.join(batch['input_names'][b].split('_')[:2])

            # word to acoustic & character to acoustic
            plot_hierarchical_attention_weights(
                aw[b][:len(word_list), :batch['x_lens'][b]],
                aw_sub[b][:len(char_list), :batch['x_lens'][b]],
                label_list=word_list,
                label_list_sub=char_list,
                spectrogram=batch['xs'][b, :, :dataset.input_freq],
                save_path=mkdir_join(save_path, speaker,
                                     batch['input_names'][b] + '.png'),
                figsize=(50, 10)
            )

            # word to characater attention
            plot_word2char_attention_weights(
                aw_dec[b][:len(word_list), :len(char_list)],
                label_list=word_list,
                label_list_sub=char_list,
                save_path=mkdir_join(save_path, speaker,
                                     batch['input_names'][b] + '_word2char.png'),
                figsize=(50, 10)
            )

            with open(join(save_path, speaker, batch['input_names'][b] + '.txt'), 'w') as f:
                f.write(batch['ys'][b][0])

        if is_new_epoch:
            break


def plot_word2char_attention_weights(attention_weights, label_list, label_list_sub,
                                     save_path=None, figsize=(10, 4)):
    """Plot attention weights from word-level decoder to character-level decoder.
    Args:
        attention_weights (np.ndarray): A tensor of size `[T_out, T_in]`
        label_list (list):
        label_list_sub (list):
        save_path (string): path to save a figure of CTC posterior (utterance)
        figsize (tuple):
    """
    plt.clf()
    plt.figure(figsize=figsize)

    # Plot attention weights
    sns.heatmap(attention_weights,
                # cmap='Blues',
                cmap='viridis',
                xticklabels=label_list_sub,
                yticklabels=label_list)
    # cbar_kws={"orientation": "horizontal"}
    plt.ylabel('Output characters (→)', fontsize=12)
    plt.ylabel('Output words (←)', fontsize=12)
    plt.yticks(rotation=0)
    plt.xticks(rotation=0)

    # Save as a png file
    if save_path is not None:
        plt.savefig(save_path, dvi=500)

    plt.close()


if __name__ == '__main__':
    main()
