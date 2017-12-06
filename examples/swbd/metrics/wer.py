#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Define evaluation method by Word Error Rate (Switchboard corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tqdm import tqdm

from utils.io.labels.word import Idx2word
from utils.evaluation.edit_distance import compute_wer, wer_align

HESITATIONS = ['uh', 'um', 'eh', 'mm', 'hm', 'ah', 'huh', 'ha', 'er', 'oof',
               'hee', 'ach', 'eee', 'ew']
LAUGHTER = 'LA'
NOISE = 'NZ'
VOCALIZED_NOISE = 'VN'
HESITATION = '%hesitation'


def do_eval_wer(model, model_type, dataset, label_type, data_size, beam_width,
                max_decode_length, eval_batch_size=None,
                progressbar=False):
    """Evaluate trained model by Word Error Rate.
    Args:
        model: the model to evaluate
        model_type (string): ctc or attention or hierarchical_ctc or
            hierarchical_attention
        dataset: An instance of a `Dataset' class
        label_type (string): word_freq1 or word_freq5 or word_freq10 or word_freq15
        data_size (string): 300h or 2000h
        beam_width: (int): the size of beam
        max_decode_length (int): the length of output sequences
            to stop prediction when EOS token have not been emitted.
            This is used for seq2seq models.
        eval_batch_size (int, optional): the batch size when evaluating the model
        progressbar (bool, optional): if True, visualize the progressbar
    Returns:
        wer_mean (float): An average of WER
    """
    batch_size_original = dataset.batch_size

    # Reset data counter
    dataset.reset()

    # Set batch size in the evaluation
    if eval_batch_size is not None:
        dataset.batch_size = eval_batch_size

    idx2word = Idx2word(
        vocab_file_path='../metrics/vocab_files/' +
        label_type + '_' + data_size + '.txt')

    wer_mean = 0
    skip_utt_num = 0
    if progressbar:
        pbar = tqdm(total=len(dataset))
    for data, is_new_epoch in dataset:

        # Create feed dictionary for next mini-batch
        if model_type in ['ctc', 'attention']:
            inputs, labels, inputs_seq_len, labels_seq_len, _ = data
        elif model_type in ['hierarchical_ctc', 'hierarchical_attention']:
            inputs, labels, _, inputs_seq_len, labels_seq_len, _, _ = data

        # Decode
        labels_pred, perm_indices = model.decode(
            inputs, inputs_seq_len,
            beam_width=beam_width,
            max_decode_length=max_decode_length)

        for i_batch in range(inputs.shape[0]):

            ##############################
            # Reference
            ##############################
            if dataset.is_test:
                str_true = labels[i_batch][0]
                # NOTE: transcript is seperated by space('_')
            else:
                # Permutate indices
                labels = labels[perm_indices]
                labels_seq_len = labels_seq_len[perm_indices]

                # Convert from list of index to string
                if model_type in ['ctc', 'hierarchical_ctc']:
                    str_true = idx2word(
                        labels[i_batch][:labels_seq_len[i_batch]])
                elif model_type in ['attention', 'hierarchical_attention']:
                    str_true = idx2word(
                        labels[i_batch][1:labels_seq_len[i_batch] - 1])
                    # NOTE: Exclude <SOS> and <EOS>

            # Remove NOISE, LAUGHTER, VOCALIZED-NOISE, HESITATION
            word_list_true = str_true.split('_')
            for i in range(len(word_list_true)):
                if word_list_true[i] in [NOISE, LAUGHTER, VOCALIZED_NOISE, HESITATION]:
                    word_list_true[i] = ''
            while '' in word_list_true:
                word_list_true.remove('')

            ##############################
            # Hypothesis
            ##############################
            str_pred = idx2word(labels_pred[i_batch])
            if model_type in ['attention', 'hierarchical_attention']:
                str_pred = str_pred.split('>')[0]
                # NOTE: Trancate by the first <EOS>

                # Remove the last space
                if len(str_pred) > 0 and str_pred[-1] == '_':
                    str_pred = str_pred[:-1]

            # Map various hesitations into a single hesitation class
            word_list_pred = str_pred.split('_')
            for i in range(len(word_list_pred)):
                if word_list_pred[i] in HESITATIONS:
                    word_list_pred[i] = HESITATION

            # Remove NOISE, LAUGHTER, VOCALIZED-NOISE, HESITATION
            for i in range(len(word_list_pred)):
                if word_list_pred[i] in HESITATIONS:
                    word_list_pred[i] = ''
                elif word_list_pred[i] in [NOISE, LAUGHTER, VOCALIZED_NOISE]:
                    word_list_pred[i] = ''
            while '' in word_list_pred:
                word_list_pred.remove('')

            # Compute WER
            if len(word_list_true) > 0:
                wer_mean += compute_wer(ref=word_list_true,
                                        hyp=word_list_pred,
                                        normalize=True)
                # if len(word_list_pred) > 0:
                #     substitute, insert, delete = wer_align(
                #         ref=word_list_true,
                #         hyp=word_list_pred)
                #     print('SUB: %d' % substitute)
                #     print('INS: %d' % insert)
                #     print('DEL: %d' % delete)
            else:
                skip_utt_num += 1

            if progressbar:
                pbar.update(1)

        if is_new_epoch:
            break

    if progressbar:
        pbar.close()

    wer_mean /= (len(dataset) - skip_utt_num)

    # Register original batch size
    if eval_batch_size is not None:
        dataset.batch_size = batch_size_original

    return wer_mean
