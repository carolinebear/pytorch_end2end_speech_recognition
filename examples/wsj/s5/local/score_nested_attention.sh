#!/bin/bash

. ./path.sh
set -e

### Select GPU
if [ $# -ne 2 ]; then
  echo "Error: set GPU number & config path." 1>&2
  echo "Usage: ./score_nested_attention.sh path_to_saved_model gpu_index" 1>&2
  exit 1
fi

### Set path to save dataset
DATA="/n/sd8/inaguma/corpus/wsj/kaldi"

saved_model_path=$1
gpu_index=$2

beam_width=4
beam_width_sub=4
length_penalty=0.1
coverage_penalty=0
resolving_unk=false
a2c_oracle=false

CUDA_VISIBLE_DEVICES=$gpu_index CUDA_LAUNCH_BLOCKING=1 \
$PYTHON exp/evaluation/eval_hierarchical.py \
  --data_save_path $DATA \
  --model_path $saved_model_path \
  --epoch -1 \
  --eval_batch_size 1 \
  --beam_width $beam_width \
  --beam_width_sub $beam_width_sub \
  --length_penalty $length_penalty \
  --coverage_penalty $coverage_penalty \
  --resolving_unk $resolving_unk \
  --a2c_oracle $a2c_oracle
