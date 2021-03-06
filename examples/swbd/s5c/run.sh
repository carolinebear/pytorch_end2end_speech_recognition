#!/bin/bash

. ./cmd.sh
. ./path.sh
set -e

. utils/parse_options.sh  # e.g. this parses the --stage option if supplied.

if [ $# -ne 2 ]; then
  echo "Error: set GPU number & config path." 1>&2
  echo "Usage: ./run.sh path_to_config_file gpu_index" 1>&2
  exit 1
fi


echo ============================================================================
echo "                           Switchboard (300h)                             "
echo ============================================================================

stage=0
# hierarchical_model=false
hierarchical_model=true
run_background=true
restart=false

### Set path to original data
SWBD_AUDIOPATH="/n/sd8/inaguma/corpus/swbd/data/LDC97S62"
EVAL2000_AUDIOPATH="/n/sd8/inaguma/corpus/swbd/data/eval2000/LDC2002S09"
EVAL2000_TRANSPATH="/n/sd8/inaguma/corpus/swbd/data/eval2000/LDC2002T43"
has_fisher=false

### Set path to save dataset
DATA="/n/sd8/inaguma/corpus/swbd/kaldi"

### Set path to save the model
MODEL="/n/sd8/inaguma/result/swbd"

### Select one tool to extract features (HTK is the fastest)
# TOOL=kaldi
TOOL=htk
# TOOL=python_speech_features
# TOOL=librosa

### Configuration of feature extranction
CHANNELS=40
WINDOW=0.025
SLIDE=0.01
ENERGY=0
DELTA=1
DELTADELTA=1
# NORMALIZE=global
NORMALIZE=speaker
# NORMALIZE=utterance


if [ ! -e $KALDI_ROOT/tools/sph2pipe_v2.5/sph2pipe ]; then
  echo ============================================================================
  echo "                           Install sph2pipe                               "
  echo ============================================================================
  SWBD_REPO=`pwd`
  # Install instructions for sph2pipe_v2.5.tar.gz
  if ! which wget >&/dev/null; then
    echo "This script requires you to first install wget";
    exit 1;
  fi
  if ! which automake >&/dev/null; then
    echo "Warning: automake not installed (IRSTLM installation will not work)"
    sleep 1
  fi
  if ! which libtoolize >&/dev/null && ! which glibtoolize >&/dev/null; then
    echo "Warning: libtoolize or glibtoolize not installed (IRSTLM installation probably will not work)"
    sleep 1
  fi

  if [ ! -e KALDI_ROOT/tools/sph2pipe_v2.5.tar.gz ]; then
    wget -T 3 -t 3 http://www.openslr.org/resources/3/sph2pipe_v2.5.tar.gz -P KALDI_ROOT/tools
  else
    echo "sph2pipe_v2.5.tar.gz is already downloaded."
  fi
  tar -xovzf KALDI_ROOT/tools/sph2pipe_v2.5.tar.gz -C $KALDI_ROOT/tools
  rm $KALDI_ROOT/tools/sph2pipe_v2.5.tar.gz
  echo "Enter into $KALDI_ROOT/tools/sph2pipe_v2.5 ..."
  cd $KALDI_ROOT/tools/sph2pipe_v2.5
  gcc -o sph2pipe *.c -lm
  echo "Get out of $KALDI_ROOT/tools/sph2pipe_v2.5 ..."
  cd $SWBD_REPO
fi


if [ $stage -le 0 ] && [ ! -e $DATA/.stage_0 ]; then
  echo ============================================================================
  echo "                           Data Preparation                               "
  echo ============================================================================

  local/swbd1_data_download.sh $SWBD_AUDIOPATH || exit 1;
  # local/swbd1_data_download.sh /mnt/matylda2/data/SWITCHBOARD_1R2 # BUT,

  # prepare SWBD dictionary first since we want to find acronyms according to pronunciations
  # before mapping lexicon and transcripts
  local/swbd1_prepare_dict.sh || exit 1;

  # Prepare Switchboard data. This command can also take a second optional argument
  # which specifies the directory to Switchboard documentations. Specifically, if
  # this argument is given, the script will look for the conv.tab file and correct
  # speaker IDs to the actual speaker personal identification numbers released in
  # the documentations. The documentations can be found here:
  # https://catalog.ldc.upenn.edu/docs/LDC97S62/
  # Note: if you are using this link, make sure you rename conv_tab.csv to conv.tab
  # after downloading.
  # Usage: local/swbd1_data_prep.sh /path/to/SWBD [/path/to/SWBD_docs]
  local/swbd1_data_prep.sh $SWBD_AUDIOPATH || exit 1;

  # Use the first 4k sentences as dev set.  Note: when we trained the LM, we used
  # the 1st 10k sentences as dev set, so the 1st 4k won't have been used in the
  # LM training data.   However, they will be in the lexicon, plus speakers
  # may overlap, so it's still not quite equivalent to a test set.
  utils/subset_data_dir.sh --first $DATA/train 4000 $DATA/dev || exit 1; # 5hr 6min
  n=$[`cat $DATA/train/segments | wc -l` - 4000]
  utils/subset_data_dir.sh --last $DATA/train $n $DATA/train_nodev || exit 1;

  # Take the first 100k utterances (just under half the data); we'll use
  # this for later stages of training.
  # utils/subset_data_dir.sh --first $DATA/train_nodev 100000 $DATA/train_100k || exit 1;
  # utils/data/remove_dup_utts.sh 200 $DATA/train_100k $DATA/train_100k_nodup || exit 1;  # 110hr

  # Finally, the full training set:
  rm -rf $DATA/train
  utils/data/remove_dup_utts.sh 300 $DATA/train_nodev $DATA/train || exit 1;  # 286hr
  rm -rf $DATA/train_nodev

  # Data preparation and formatting for eval2000 (note: the "text" file
  # is not very much preprocessed; for actual WER reporting we'll use
  # sclite.
  local/eval2000_data_prep.sh $EVAL2000_AUDIOPATH $EVAL2000_TRANSPATH || exit 1;

  # prepare the rt03 data.  Note: this isn't 100% necessary for this
  # recipe, not all parts actually test using rt03.
  # local/rt03_data_prep.sh /export/corpora/LDC/LDC2007S10

  touch $DATA/.stage_0
  echo "Finish data preparation (stage: 0)."
fi


if [ $stage -le 1 ] && [ ! -e $DATA/.stage_1 ]; then
  echo ============================================================================
  echo "                        Feature extranction                               "
  echo ============================================================================

  if [ $TOOL = "kaldi" ]; then
    for x in train dev eval2000; do
      steps/make_fbank.sh --nj 8 --cmd run.pl $DATA/$x exp/make_fbank/$x $DATA/fbank || exit 1;
      steps/compute_cmvn_stats.sh $DATA/$x exp/make_fbank/$x $DATA/fbank || exit 1;
      utils/fix_data_dir.sh $DATA/$x || exit 1;
    done

  else
    # Convert .sph (2ch) to .wav (1ch)
    if [ ! -e $DATA/wav_1ch/.done_wav_1ch ]; then
      # train, dev set
      train_sph_paths=$(find $SWBD_AUDIOPATH/. -iname '*.sph')
      mkdir -p $DATA/wav_1ch/train
      for sph_path in $train_sph_paths ; do
        file_name=$(basename $sph_path)
        base=${file_name%.*}
        ext=${file_name##*.}
        wav_path_A=$DATA/wav_1ch/train/$base"-A.wav"
        wav_path_B=$DATA/wav_1ch/train/$base"-B.wav"
        echo "Converting from "$sph_path" to "$wav_path_A
        $KALDI_ROOT/tools/sph2pipe_v2.5/sph2pipe -f wav -p -c 1 $sph_path $wav_path_A || exit 1;
        echo "Converting from "$sph_path" to "$wav_path_B
        $KALDI_ROOT/tools/sph2pipe_v2.5/sph2pipe -f wav -p -c 2 $sph_path $wav_path_B || exit 1;
      done

      # eval2000
      eval2000_sph_paths=$(find $EVAL2000_AUDIOPATH/. -iname '*.sph')
      mkdir -p $DATA/wav_1ch/eval2000
      for sph_path in $eval2000_sph_paths ; do
        file_name=$(basename $sph_path)
        base=${file_name%.*}
        ext=${file_name##*.}
        wav_path_A=$DATA/wav_1ch/eval2000/$base"-A.wav"
        wav_path_B=$DATA/wav_1ch/eval2000/$base"-B.wav"
        echo "Converting from "$sph_path" to "$wav_path_A
        $KALDI_ROOT/tools/sph2pipe_v2.5/sph2pipe -f wav -p -c 1 $sph_path $wav_path_A || exit 1;
        echo "Converting from "$sph_path" to "$wav_path_B
        $KALDI_ROOT/tools/sph2pipe_v2.5/sph2pipe -f wav -p -c 2 $sph_path $wav_path_B || exit 1;
      done

      touch $DATA/wav_1ch/.done_wav_1ch
    fi

    if [ $TOOL = "htk" ]; then
      # Make a config file to covert from wav to htk file
      # and split per channel
      python local/make_htk_config.py \
          --data_save_path $DATA \
          --config_save_path ./conf/fbank_htk.conf \
          --channels $CHANNELS \
          --window $WINDOW \
          --slide $SLIDE \
          --energy $ENERGY \
          --delta $DELTA \
          --deltadelta $DELTADELTA || exit 1;

      # Convert from wav to htk files
      for data_type in train dev eval2000 ; do
        mkdir -p $DATA/htk
        mkdir -p $DATA/htk/$data_type

        if [ ! -e $DATA/htk/$data_type/.done_make_htk ]; then
          $HCOPY -T 1 -C ./conf/fbank_htk.conf -S $DATA/$data_type/wav2htk.scp || exit 1;
          touch $DATA/htk/$data_type/.done_make_htk
        fi
      done

    else
      if ! which sox >&/dev/null; then
        echo "This script requires you to first install sox";
        exit 1;
      fi
    fi
  fi

  python local/feature_extraction.py \
    --data_save_path $DATA \
    --tool $TOOL \
    --normalize $NORMALIZE \
    --channels $CHANNELS \
    --window $WINDOW \
    --slide $SLIDE \
    --energy $ENERGY \
    --delta $DELTA \
    --deltadelta $DELTADELTA || exit 1;

  touch $DATA/.stage_1
  echo "Finish feature extranction (stage: 1)."
fi


if [ $stage -le 2 ] && [ ! -e $DATA/.stage_2 ]; then
  echo ============================================================================
  echo "                            Create dataset                                "
  echo ============================================================================

  python local/make_dataset_csv.py \
    --data_save_path $DATA \
    --tool $TOOL || exit 1;

  touch $DATA/.stage_2
  echo "Finish creating dataset (stage: 2)."
fi


if [ $stage -le 3 ]; then
  echo ============================================================================
  echo "                             Training stage                               "
  echo ============================================================================

  config_path=$1
  gpu_index=$2
  filename=$(basename $config_path | awk -F. '{print $1}')

  mkdir -p log
  mkdir -p $MODEL

  echo "Start training..."

  if $hierarchical_model; then
    if $restart; then
      if $run_background; then
        CUDA_VISIBLE_DEVICES=$gpu_index CUDA_LAUNCH_BLOCKING=1 \
        nohup $PYTHON exp/training/train_hierarchical.py \
          --gpu $gpu_index \
          --saved_model_path $config_path \
          --data_save_path $DATA > log/$filename".log" &
      else
        CUDA_VISIBLE_DEVICES=$gpu_index CUDA_LAUNCH_BLOCKING=1 \
        nohup $PYTHON exp/training/train_hierarchical.py \
          --gpu $gpu_index \
          --saved_model_path $config_path \
          --data_save_path $DATA || exit 1;
      fi
    else
      if $run_background; then
        CUDA_VISIBLE_DEVICES=$gpu_index CUDA_LAUNCH_BLOCKING=1 \
        nohup $PYTHON exp/training/train_hierarchical.py \
          --gpu $gpu_index \
          --config_path $config_path \
          --model_save_path $MODEL \
          --data_save_path $DATA > log/$filename".log" &
      else
        CUDA_VISIBLE_DEVICES=$gpu_index CUDA_LAUNCH_BLOCKING=1 \
        $PYTHON exp/training/train_hierarchical.py \
          --gpu $gpu_index \
          --config_path $config_path \
          --model_save_path $MODEL \
          --data_save_path $DATA || exit 1;
      fi
    fi
  else
    if $restart; then
      if $run_background; then
        CUDA_VISIBLE_DEVICES=$gpu_index CUDA_LAUNCH_BLOCKING=1 \
        nohup $PYTHON exp/training/train.py \
          --gpu $gpu_index \
          --saved_model_path $config_path \
          --data_save_path $DATA > log/$filename".log" &
      else
        CUDA_VISIBLE_DEVICES=$gpu_index CUDA_LAUNCH_BLOCKING=1 \
        $PYTHON exp/training/train.py \
          --gpu $gpu_index \
          --saved_model_path $config_path \
          --data_save_path $DATA || exit 1;
      fi
    else
      if $run_background; then
        CUDA_VISIBLE_DEVICES=$gpu_index CUDA_LAUNCH_BLOCKING=1 \
        nohup $PYTHON exp/training/train.py \
          --gpu $gpu_index \
          --config_path $config_path \
          --model_save_path $MODEL \
          --data_save_path $DATA > log/$filename".log" &
      else
        CUDA_VISIBLE_DEVICES=$gpu_index CUDA_LAUNCH_BLOCKING=1 \
        $PYTHON exp/training/train.py \
          --gpu $gpu_index \
          --config_path $config_path \
          --model_save_path $MODEL \
          --data_save_path $DATA　|| exit 1;
      fi
    fi
  fi

  echo "Finish model training (stage: 3)."
fi


if [ $stage -le 4 ]; then
  echo ============================================================================
  echo "                             LM training                                 "
  echo ============================================================================

  echo "Finish LM training (stage: 4)."
fi


if [ $stage -le 5 ]; then
  echo ============================================================================
  echo "                              Rescoring                                   "
  echo ============================================================================

  echo "Finish rescoring (stage: 5)."
fi


echo "Done."


# utils/prepare_lang.sh data/local/dict_nosp \
#                         "<unk>"  data/local/lang_nosp data/lang_nosp

# Now train the language models. We are using SRILM and interpolating with an
# LM trained on the Fisher transcripts (part 2 disk is currently missing; so
# only part 1 transcripts ~700hr are used)

# If you have the Fisher data, you can set this "fisher_dir" variable.
# fisher_dirs="/export/corpora3/LDC/LDC2004T19/fe_03_p1_tran/ /export/corpora3/LDC/LDC2005T19/fe_03_p2_tran/"
# fisher_dirs="/exports/work/inf_hcrc_cstr_general/corpora/fisher/transcripts" # Edinburgh,
# fisher_dirs="/mnt/matylda2/data/FISHER/fe_03_p1_tran /mnt/matylda2/data/FISHER/fe_03_p2_tran" # BUT,
# local/swbd1_train_lms.sh $DATA/local/train/text \
#                          $DATA/local/dict_nosp/lexicon.txt $DATA/local/lm $fisher_dirs


# getting results (see RESULTS file)
# for x in 1 2 3a 3b 4a; do grep 'Percent Total Error' exp/tri$x/decode_eval2000_sw1_tg/score_*/eval2000.ctm.filt.dtl | sort -k5 -g | head -1; done
