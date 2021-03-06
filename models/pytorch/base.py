#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Base class for all models (pytorch)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
from os.path import join, isfile, basename
from glob import glob
import numpy as np

import logging
logger = logging.getLogger('training')

import torch
import torch.nn as nn
import torch.optim as optim

from models.pytorch.tmp.lr_scheduler import ReduceLROnPlateau
from utils.directory import mkdir

OPTIMIZER_CLS_NAMES = {
    "sgd": optim.SGD,
    "momentum": optim.SGD,
    "nesterov": optim.SGD,
    "adam": optim.Adam,
    "adadelta": optim.Adadelta,
    "adagrad": optim.Adagrad,
    "rmsprop": optim.RMSprop
}


class ModelBase(nn.Module):
    """A base class for all models. All models have to inherit this class."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError

    def forward(self, inputs):
        raise NotImplementedError

    def init_weights(self, parameter_init, distribution,
                     keys=[None], ignore_keys=[None]):
        """Initialize parameters.
        Args:
            parameter_init (float):
            distribution (string): uniform or normal or orthogonal or constant
            keys (list, optional):
            ignore_keys (list, optional):
        """
        for name, param in self.named_parameters():
            if keys != [None] and len(list(filter(lambda k: k in name, keys))) == 0:
                continue

            if ignore_keys != [None] and len(list(filter(lambda k: k in name, ignore_keys))) > 0:
                continue

            if distribution == 'uniform':
                nn.init.uniform_(
                    param.data, a=-parameter_init, b=parameter_init)
            elif distribution == 'normal':
                assert parameter_init > 0
                torch.nn.init.normal_(param.data, mean=0, std=parameter_init)
            elif distribution == 'orthogonal':
                if param.dim() >= 2:
                    torch.nn.init.orthogonal_(param.data, gain=1)
            elif distribution == 'constant':
                torch.nn.init.constant_(param.data, val=parameter_init)
            else:
                raise NotImplementedError

    def init_forget_gate_bias_with_one(self):
        """Initialize bias in forget gate with 1. See detail in
            https://discuss.pytorch.org/t/set-forget-gate-bias-of-lstm/1745
        """
        for name, param in self.named_parameters():
            if 'lstm' in name and 'bias' in name:
                n = param.size(0)
                start, end = n // 4, n // 2
                param.data[start:end].fill_(1.)

    def inject_weight_noise(self, mean, std):
        # m = torch.distributions.Normal(
        #     torch.Tensor([mean]), torch.Tensor([std]))
        # for name, param in self.named_parameters():
        #     noise = m.sample()
        #     param.data += noise.to(self.device)

        for name, param in self.named_parameters():
            noise = np.random.normal(loc=mean, scale=std, size=param.size())
            noise = torch.FloatTensor(noise)
            param.data += noise.to(self.device)

    @property
    def num_params_dict(self):
        if not hasattr(self, '_num_params_dict'):
            self._num_params_dict = {}
            for name, param in self.named_parameters():
                self._num_params_dict[name] = param.view(-1).size(0)
        return self._num_params_dict

    @property
    def total_parameters(self):
        if not hasattr(self, '_num_params'):
            self._num_params = 0
            for name, param in self.named_parameters():
                self._num_params += param.view(-1).size(0)
        return self._num_params

    @property
    def use_cuda(self):
        return torch.cuda.is_available()

    @property
    def device(self):
        return torch.device("cuda:0" if self.use_cuda else "cpu")

    def set_cuda(self, deterministic=False, benchmark=True):
        """Set model to the GPU version.
        Args:
            deterministic (bool, optional):
            benchmark (bool, optional):
        """
        if self.use_cuda:
            if benchmark:
                torch.backends.cudnn.benchmark = True
                logger.info('GPU mode (benchmark)')
            elif deterministic:
                logger.info('GPU deterministic mode (no cudnn)')
                torch.backends.cudnn.enabled = False
                # NOTE: this is slower than GPU mode.
            else:
                logger.info('GPU mode')
            self = self.to(self.device)
        else:
            logger.info('CPU mode')

    def set_optimizer(self, optimizer, learning_rate_init,
                      weight_decay=0, clip_grad_norm=5,
                      lr_schedule=True, factor=0.1, patience_epoch=5):
        """Set optimizer.
        Args:
            optimizer (string): sgd or adam or adadelta or adagrad or rmsprop
            learning_rate_init (float): An initial learning rate
            weight_decay (float, optional): L2 penalty
            clip_grad_norm (float): not used here
            lr_schedule (bool, optional): if True, wrap optimizer with
                scheduler. Default is True.
            factor (float, optional):
            patience_epoch (int, optional):
        Returns:
            scheduler ():
        """
        optimizer = optimizer.lower()
        if optimizer not in OPTIMIZER_CLS_NAMES:
            raise ValueError(
                "Optimizer name should be one of [%s], you provided %s." %
                (", ".join(OPTIMIZER_CLS_NAMES), optimizer))

        if optimizer == 'sgd':
            self.optimizer = optim.SGD(self.parameters(),
                                       lr=learning_rate_init,
                                       weight_decay=weight_decay,
                                       nesterov=False)
        elif optimizer == 'momentum':
            self.optimizer = optim.SGD(self.parameters(),
                                       lr=learning_rate_init,
                                       momentum=0.9,
                                       weight_decay=weight_decay,
                                       nesterov=False)
        elif optimizer == 'nesterov':
            self.optimizer = optim.SGD(self.parameters(),
                                       lr=learning_rate_init,
                                       momentum=0.9,
                                       weight_decay=weight_decay,
                                       nesterov=True)
        elif optimizer == 'adadelta':
            self.optimizer = optim.Adadelta(
                self.parameters(),
                # rho=0.9,  # default
                rho=0.95,
                # eps=1e-6,  # default
                eps=1e-8,
                lr=learning_rate_init,
                weight_decay=weight_decay)

        else:
            self.optimizer = OPTIMIZER_CLS_NAMES[optimizer](
                self.parameters(),
                lr=learning_rate_init,
                weight_decay=weight_decay)

        if lr_schedule:
            # scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            scheduler = ReduceLROnPlateau(
                self.optimizer,
                mode='min',
                factor=factor,
                patience=patience_epoch,
                verbose=False,
                threshold=0.0001,
                threshold_mode='rel',
                cooldown=0,
                min_lr=0,
                eps=1e-08)
            # TODO: fix bug
        else:
            scheduler = None

        return scheduler

    def set_save_path(self, save_path):
        # Reset model directory
        model_index = 0
        save_path_tmp = save_path
        while True:
            if isfile(join(save_path_tmp, 'complete.txt')):
                # Training of the first model have been finished
                model_index += 1
                save_path_tmp = save_path + '_' + str(model_index)
            elif isfile(join(save_path_tmp, 'config.yml')):
                # Training of the first model have not been finished yet
                model_index += 1
                save_path_tmp = save_path + '_' + str(model_index)
            else:
                break
        self.save_path = mkdir(save_path_tmp)

    def save_checkpoint(self, save_path, epoch, step, lr, metric_dev_best,
                        remove_old_checkpoints=False):
        """Save checkpoint.
        Args:
            save_path (string): path to save a model (directory)
            epoch (int): the currnet epoch
            step (int): the current step
            lr (float):
            metric_dev_best (float):
            remove_old_checkpoints (bool, optional): if True, all checkpoints
                other than the best one will be deleted
        Returns:
            model (string): path to the saved model (file)
        """
        model_path = join(save_path, 'model.epoch-' + str(epoch))

        # Remove old checkpoints
        if remove_old_checkpoints:
            for path in glob(join(save_path, 'model.epoch-*')):
                os.remove(path)

        # Save parameters, optimizer, step index etc.
        checkpoint = {
            "state_dict": self.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "epoch": epoch,
            "step": step,
            "lr": lr,
            "metric_dev_best": metric_dev_best
        }
        torch.save(checkpoint, model_path)

        logger.info("=> Saved checkpoint (epoch:%d): %s" % (epoch, model_path))

    def load_checkpoint(self, save_path, epoch=-1, restart=False,
                        load_pretrained_model=False):
        """Load checkpoint.
        Args:
            save_path (string): path to the saved models
            epoch (int, optional): if -1 means the last saved model
            restart (bool, optional): if True, restore the save optimizer
            load_pretrained_model (bool, optional): if True, load all parameters
                which match those of the new model's parameters
        Returns:
            epoch (int): the currnet epoch
            step (int): the current step
            lr (float):
            metric_dev_best (float)
        """
        if int(epoch) == -1:
            # Restore the last saved model
            epochs = [(int(basename(x).split('-')[-1]), x)
                      for x in glob(join(save_path, 'model.*'))]

            if len(epochs) == 0:
                raise ValueError

            epoch = sorted(epochs, key=lambda x: x[0])[-1][0]

        model_path = join(save_path, 'model.epoch-' + str(epoch))

        if isfile(model_path):
            checkpoint = torch.load(
                model_path, map_location=lambda storage, loc: storage)

            # Restore parameters
            if load_pretrained_model:
                logger.info(
                    "=> Loading pre-trained checkpoint (epoch:%d): %s" % (epoch, model_path))

                pretrained_dict = checkpoint['state_dict']
                model_dict = self.state_dict()

                # 1. filter out unnecessary keys and params which do not match size
                pretrained_dict = {
                    k: v for k, v in pretrained_dict.items() if k in model_dict.keys() and v.size() == model_dict[k].size()}
                # 2. overwrite entries in the existing state dict
                model_dict.update(pretrained_dict)
                # 3. load the new state dict
                self.load_state_dict(model_dict)

                for k in pretrained_dict.keys():
                    logger.info(k)
                logger.info('=> Finished loading.')
            else:
                self.load_state_dict(checkpoint['state_dict'])

            # Restore optimizer
            if restart:
                logger.info("=> Loading checkpoint (epoch:%d): %s" %
                            (epoch, model_path))

                if hasattr(self, 'optimizer'):
                    self.optimizer.load_state_dict(checkpoint['optimizer'])

                    for state in self.optimizer.state.values():
                        for k, v in state.items():
                            if torch.is_tensor(v):
                                state[k] = v.to(self.device)
                    # NOTE: from https://github.com/pytorch/pytorch/issues/2830
                else:
                    raise ValueError('Set optimizer.')
            else:
                print("=> Loading checkpoint (epoch:%d): %s" %
                      (epoch, model_path))
        else:
            raise ValueError("No checkpoint found at %s" % model_path)

        return (checkpoint['epoch'] + 1, checkpoint['step'] + 1,
                checkpoint['lr'], checkpoint['metric_dev_best'])

    def _create_tensor(self, size, fill_value=0, dtype=torch.float):
        """Initialize a variable with zero.
        Args:
            size (tuple):
            fill_value (int or float, optional):
            dtype ():
        Returns:
            tensor (torch.Tensor):
        """
        tensor = torch.zeros(size, dtype=dtype).fill_(fill_value)
        return tensor.to(self.device)

    def np2tensor(self, array, dtype=torch.float, cpu=False):
        """Convert form np.ndarray to Variable.
        Args:
            array (np.ndarray): A tensor of any sizes
            type (string, optional): float or long or int
            cpu (bool, optional):
        Returns:
            array (torch.Tensor):
        """
        if isinstance(array, list):
            array = np.array(array)

        tensor = torch.from_numpy(array)
        if dtype is not None:
            if dtype == torch.float:
                tensor = tensor.float()
            elif dtype == torch.long:
                tensor = tensor.long()
            elif dtype == torch.int:
                tensor = tensor.int()

        if cpu:
            return tensor
        else:
            return tensor.to(self.device)

    def tensor2np(self, tensor):
        """Convert form Variable to np.ndarray.
        Args:
            tensor (torch.Tensor):
        Returns:
            np.ndarray
        """
        return tensor.cpu().numpy()
