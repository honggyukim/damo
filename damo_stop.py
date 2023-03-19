#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0

"""
Stop DAMON.
"""

import _damon
import _damon_args

def set_argparser(parser):
    return _damon_args.set_common_argparser(parser)

def main(args=None):
    if not args:
        parser = set_argparser(parser)
        args = parser.parse_args()

    _damon.ensure_root_and_initialized(args)

    running_kdamond_names = _damon.running_kdamond_names()
    if len(running_kdamond_names) == 0:
        print('DAMON is not turned on')
        exit(1)

    err = _damon.turn_damon_off(running_kdamond_names)
    if err:
        print('DAMON turn off failed (%s)' % err)

if __name__ == '__main__':
    main()
