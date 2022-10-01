#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0

"""
Contains core functions for DAMON sysfs control.
"""

import os
import time
import traceback

import _damo_fs
import _damon

feature_supports = None

# Use only one kdamond, one context, and one target for now
root_dir = '/sys/kernel/mm/damon'
admin_dir = os.path.join(root_dir, 'admin')
kdamonds_dir = os.path.join(admin_dir, 'kdamonds')
nr_kdamonds_file = os.path.join(kdamonds_dir, 'nr_kdamonds')

def kdamond_dir_of(kdamond_idx):
    return os.path.join(admin_dir, 'kdamonds', '%s' % kdamond_idx)

def state_file_of(kdamond_idx):
    return os.path.join(kdamond_dir_of(kdamond_idx), 'state')

def nr_contexts_file_of(kdamond_idx):
    return os.path.join(kdamond_dir_of(kdamond_idx), 'contexts', 'nr_contexts')

def ctx_dir_of(kdamond_idx, context_idx):
    return os.path.join(kdamond_dir_of(kdamond_idx), 'contexts', '%s' %
            context_idx)

def schemes_dir_of(kdamond_idx, context_idx):
    return os.path.join(ctx_dir_of(kdamond_idx, context_idx), 'schemes')

def nr_schemes_file_of(kdamond_idx, context_idx):
    return os.path.join(schemes_dir_of(kdamond_idx, context_idx), 'nr_schemes')

def targets_dir_of(kdamond_idx, context_idx):
    return os.path.join(ctx_dir_of(kdamond_idx, context_idx), 'targets')

def nr_targets_file_of(kdamond_idx, context_idx):
    return os.path.join(targets_dir_of(kdamond_idx, context_idx), 'nr_targets')

def target_dir_of(kdamond_idx, context_idx, target_idx):
    return os.path.join(ctx_dir_of(kdamond_idx, context_idx), 'targets', '%s' %
            target_idx)

def regions_dir_of(kdamond_idx, context_idx, target_idx):
    return os.path.join(target_dir_of(kdamond_idx, context_idx, target_idx),
            'regions')

def nr_regions_file_of(kdamond_idx, context_idx, target_idx):
    return os.path.join(regions_dir_of(kdamond_idx, context_idx, target_idx),
            'nr_regions')

def __turn_damon(kdamond_idx, on_off):
    err = _damo_fs.write_file(state_file_of(kdamond_idx), on_off)
    if err != None:
        print(err)
        return 1
    return 0

def turn_damon(on_off):
    if on_off == 'on':
        # In case of vaddr, too early monitoring shows unstable mapping changes.
        # Give the process a time to have stable memory mapping.
        time.sleep(0.5)
    return __turn_damon(0, on_off)

def __is_damon_running(kdamond_idx):
    content, err = _damo_fs.read_file(os.path.join(
        kdamond_dir_of(kdamond_idx), 'state'))
    if err != None:
        print(err)
        return False
    return content.strip() == 'on'

def is_damon_running():
    return __is_damon_running(0)

def wops_for_monitoring_attrs(ctx):
    return {
        'intervals': {
            'sample_us': '%d' % ctx.intervals.sample,
            'aggr_us': '%d' % ctx.intervals.aggr,
            'update_us': '%d' % ctx.intervals.ops_update,
        },
        'nr_regions': {
            'min': '%d' % ctx.nr_regions.min_nr_regions,
            'max': '%d' % ctx.nr_regions.max_nr_regions,
        },
    }

def wops_for_scheme_access_pattern(pattern, ctx):
    max_nr_accesses = ctx.intervals.aggr / ctx.intervals.sample

    return {
        'sz': {
            'min': '%d' % pattern.min_sz_bytes,
            'max': '%d' % pattern.max_sz_bytes,
        },
        'nr_accesses': {
            'min': '%d' % int(
                pattern.min_nr_accesses_permil * max_nr_accesses / 1000),
            'max': '%d' % int(
                pattern.max_nr_accesses_permil * max_nr_accesses / 1000),
        },
        'age': {
            'min': '%d' % (pattern.min_age_us / ctx.intervals.aggr),
            'max': '%d' % (pattern.max_age_us / ctx.intervals.aggr),
        },
    }

def wops_for_scheme_quotas(quotas):
    return {
        'ms': '%d' % quotas.time_ms,
        'bytes': '%d' % quotas.sz_bytes,
        'reset_interval_ms': '%d' % quotas.reset_interval_ms,
        'weights': {
            'sz_permil': '%d' % quotas.weight_sz_permil,
            'nr_accesses_permil': '%d' % quotas.weight_nr_accesses_permil,
            'age_permil': '%d' % quotas.weight_age_permil,
        },
    }

def wops_for_scheme_watermarks(wmarks):
    return {
        'metric': wmarks.metric,
        'interval_us': '%d' % wmarks.interval_us,
        'high': '%d' % wmarks.high_permil,
        'mid': '%d' % wmarks.mid_permil,
        'low': '%d' % wmarks.low_permil,
    }

def wops_for_schemes(ctx):
    schemes = ctx.schemes

    schemes_wops = {}
    for idx, scheme in enumerate(schemes):
        schemes_wops['%d' % idx] = {
            'access_pattern': wops_for_scheme_access_pattern(
                scheme.access_pattern, ctx),
            'action': scheme.action,
            'quotas': wops_for_scheme_quotas(scheme.quotas),
            'watermarks': wops_for_scheme_watermarks(scheme.watermarks),
        }
    return schemes_wops

def ensure_dirs_populated2(kdamonds):
    wops = []
    nr_kdamonds, err = _damo_fs.read_file(nr_kdamonds_file)
    if err != None:
        return err
    if int(nr_kdamonds) != len(kdamonds):
        wops += [{nr_kdamonds_file: '%d' % len(kdamonds)}]
    for kd_idx, kdamond in enumerate(kdamonds):
        nr_contexts, err = _damo_fs.read_file(nr_contexts_file_of(kd_idx))
        if err != None:
            return err
        if int(nr_contexts) != len(kdamond.contexts):
            wops += [{nr_contexts_file_of(kd_idx):
                '%d' % len(kdamond.contexts)}]
        for ctx_idx, ctx in enumerate(kdamond.contexts):
            nr_targets, err = _damo_fs.read_file(
                    nr_targets_file_of(kd_idx, ctx_idx))
            if err != None:
                return err
            if int(nr_targets) != len(ctx.targets):
                wops += [{nr_targets_file_of(kd_idx, ctx_idx):
                    '%d' % len(ctx.targets)}]
            for target_idx, target in enumerate(ctx.targets):
                nr_regions, err = _damo_fs.read_file(
                        nr_regions_file_of(kd_idx, ctx_idx, target_idx))
                if err != None:
                    return err
                if int(nr_regions) != len(target.regions):
                    wops += [{nr_regions_file_of(kd_idx, ctx_idx, target_idx):
                        '%d' % len(target.regions)}]
        nr_schemes, err = _damo_fs.read_file(
                nr_schemes_file_of(kd_idx, ctx_idx))
        if err != None:
            return err
        if int(nr_schemes) != len(ctx.schemes):
            wops += [{nr_schemes_file_of(kd_idx, ctx_idx):
                '%d' % len(ctx.schemes)}]

    return _damo_fs.write_files(wops)

def wops_for_targets(ctx):
    wops = {}
    for target_idx, target in enumerate(ctx.targets):
        target_wops = {}
        if _damon.target_has_pid(ctx.ops):
            target_wops['pid_target'] = '%s' % target.pid
        wops['%d' % target_idx] = target_wops

        regions_wops = {}
        target_wops['regions'] = regions_wops
        for idx, region in enumerate(target.regions):
            region_wops = {
                    'start': '%d' % region.start,
                    'end': '%d' % region.end
            }
            regions_wops['%d' % idx] = region_wops
    return wops

def wops_for_ctx(ctx):
    return [
            {'operations': ctx.ops},
            {'monitoring_attrs': wops_for_monitoring_attrs(ctx)},
            {'targets': wops_for_targets(ctx)},
            {'schemes': wops_for_schemes(ctx)},
    ]

def wops_for_ctxs(ctxs):
    ctxs_wops = {}
    for ctx_id, ctx in enumerate(ctxs):
        ctxs_wops['%d' % ctx_id] = wops_for_ctx(ctx)
    return ctxs_wops

def wops_for_kdamond(kdamond):
    return {'contexts': wops_for_ctxs(kdamond.contexts)}

def wops_for_kdamonds(kdamonds):
    kdamonds_wops = {}
    for kd_idx, kdamond in enumerate(kdamonds):
        kdamonds_wops['%d' % kd_idx] = wops_for_kdamond(kdamond)
    return kdamonds_wops

def apply_kdamonds(kdamonds):
    if len(kdamonds) != 1:
        print('currently only one kdamond is supported')
        exit(1)
    if len(kdamonds[0].contexts) != 1:
        print('currently only one damon_ctx is supported')
        exit(1)
    if len(kdamonds[0].contexts[0].targets) != 1:
        print('currently only one target is supported')
        exit(1)
    err = ensure_dirs_populated2(kdamonds)
    if err != None:
        print(err)
        print('directory populating failed')
        exit(1)

    err = _damo_fs.write_files({kdamonds_dir: wops_for_kdamonds(kdamonds)})
    if err != None:
        print('kdamond applying failed: %s' % err)
        traceback.print_exc()
        return 1

def __commit_inputs(kdamond_idx):
    err = _damo_fs.write_file(state_file_of(kdamond_idx), 'commit')
    if err != None:
        print(err)
        return 1
    return 0

def commit_inputs():
    return __commit_inputs(0)

def feature_supported(feature):
    if feature_supports == None:
        update_supported_features()
    return feature_supports[feature]

def dirs_populated_for(kdamond_idx, ctx_idx):
    files_to_read = {nr_kdamonds_file: None,
            nr_contexts_file_of(kdamond_idx): None,
            nr_targets_file_of(kdamond_idx, ctx_idx): None}
    err = _damo_fs.read_files_of(files_to_read)
    if err:
        print(err)
        return False
    return (int(files_to_read[nr_kdamonds_file]) >= 1 and
            int(files_to_read[nr_contexts_file_of(kdamond_idx)]) >= 1 and
            int(files_to_read[nr_targets_file_of(kdamond_idx, ctx_idx)]) >= 1)

def dirs_populated():
    return dirs_populated_for(0, 0)

def ensure_dirs_populated_for(kdamond_idx, context_idx):
    if dirs_populated():
        return

    wops = [{nr_kdamonds_file: '1'},
            {nr_contexts_file_of(kdamond_idx): '1'},
            {nr_targets_file_of(kdamond_idx, context_idx): '1'}]
    err = _damo_fs.write_files(wops)
    if err != None:
        print(err)
        print('failed populating kdamond and context dirs')
        exit(1)

def ensure_dirs_populated():
    return ensure_dirs_populated_for(0, 0)

def damon_sysfs_missed():
    'Return none-None if DAMON sysfs interface is not found'
    if not os.path.isdir(kdamonds_dir):
        return 'damon sysfs dir (%s) not found' % kdamonds_dir
    return None

def update_supported_features():
    global feature_supports

    if feature_supports != None:
        return None
    feature_supports = {x: False for x in _damon.features}

    missed = damon_sysfs_missed()
    if missed != None:
        return missed
    feature_supports = {x: True for x in _damon.features}
    feature_supports['record'] = False

    ensure_dirs_populated()
    avail_operations_filepath = os.path.join(ctx_dir_of(0, 0),
            'avail_operations')
    if not os.path.isfile(avail_operations_filepath):
        for feature in ['vaddr', 'paddr', 'fvaddr', 'vaddr']:
            operations_filepath = os.path.join(ctx_dir_of(0, 0), 'operations')
            err = _damo_fs.write_file(operations_filepath, feature)
            if err != None:
                feature_supports[feature] = False
            else:
                feature_supports[feature] = True
        return None

    content, err = _damo_fs.read_file(avail_operations_filepath)
    if err != None:
        print(err)
        return None
    avail_ops = content.strip().split()
    for feature in ['vaddr', 'paddr', 'fvaddr']:
        feature_supports[feature] = feature in avail_ops

    return None

def initialize(skip_dirs_population=False):
    err = update_supported_features()
    if err:
        return err
    return None
