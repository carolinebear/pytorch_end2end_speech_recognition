#! /usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging


def set_logger(save_path, restart=False):
    """Set logger.
    Args:
        save_path (string):
        restart (bool, optional):
    Returns:
        logger ():
    """
    logger = logging.getLogger('training')
    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    if restart:
        i = 1
        while True:
            log_file_name = os.path.join(
                save_path, 'train_restart' + str(i) + '.log')
            if os.path.isfile(log_file_name):
                i += 1
            else:
                break
    else:
        log_file_name = os.path.join(save_path, 'train.log')
    fh = logging.FileHandler(log_file_name)
    fh.setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s line:%(lineno)d %(levelname)s:  %(message)s')
    sh.setFormatter(formatter)
    fh.setFormatter(formatter)
    logger.addHandler(sh)
    logger.addHandler(fh)

    return logger
