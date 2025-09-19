"""
DOCSTRING for first public console interface.

USAGE:
    xdmod-preprocess -c [PATH TO CONFIG FILE] -r [RESOURCE]
"""

import logging
import gzip
import json
import stat
import csv
import os
import argparse
import tempfile
import shutil
import pandas as pd

from preprocessor.lib import helpers


def process_anvil(filep, fullpath, filename, dest_dir, _):
    delimiter = '|'
    reader = csv.reader(filep, delimiter=delimiter)

    srcstat = os.stat(fullpath)

    tmpfiles = {}

    for line in reader:
        if not line[5].startswith('ai'):
            continue

        queue = line[3]
        if queue.lower().startswith('gpu'):
            resource = 'Purdue-Anvil-GPU'
        else:
            resource = 'Purdue-Anvil-CPU'

        if len(line) > 26:
            line[25] = "!".join(line[25:])

        line[5] = 'NAIRR' + line[5][2:8]

        if resource not in tmpfiles:
            tmpfiles[resource] = tempfile.NamedTemporaryFile(mode="w", encoding="utf=8", delete=False)

        tmpfiles[resource].write('|'.join(line[0:26]) + "\n")

    for resource, tmpfile in tmpfiles.items():
        if not os.path.exists(os.path.join(dest_dir, resource)):
            os.mkdir(os.path.join(dest_dir, resource))
        tmpname = tmpfile.name
        tmpfile.close()
        target = os.path.join(dest_dir, resource, filename)
        shutil.move(tmpname, target)
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        os.utime(target, (srcstat[stat.ST_ATIME], srcstat[stat.ST_MTIME]))


def process_json(filep, fullpath, filename, dest_dir, translator):

    try:
        slurm_log = json.load(filep)
        logging.debug(f"Processing {filename}")
    except json.decoder.JSONDecodeError:
        logging.warning("Unable to JSON decode " + fullpath)
        return

    srcstat = os.stat(fullpath)

    outdata = {}

    for job in slurm_log['jobs']:

        charge_id, resource = translator.translate(job, fullpath)

        if charge_id is not None:
            job['account'] = charge_id

            if resource not in outdata:
                outdata[resource] = []

            outdata[resource].append(job)

    for resource_name, out_jobs in outdata.items():
        if not os.path.exists(os.path.join(dest_dir, resource_name)):
            os.mkdir(os.path.join(dest_dir, resource_name))

        output = {'jobs':  out_jobs}
        outfilename = filename[:-3] if filename.endswith('.gz') else filename
        target = os.path.join(dest_dir, resource_name, outfilename)
        with open(target, 'w', encoding="utf=8") as outfp:
            json.dump(output, outfp)

        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        os.utime(target, (srcstat[stat.ST_ATIME], srcstat[stat.ST_MTIME]))

        logging.info("Wrote " + outfilename)

def main():

    parser = argparse.ArgumentParser(
        prog='xdmod-preprocess',
        description='Manages resource manager log files',
        epilog='')

    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('-q', '--quiet', action='store_true', help='Show only warnings and errors')
    parser.add_argument('-c', '--config', type=str, default='config.json', help='The full path to the configuration file.')
    parser.add_argument('resource', help='The name of the resource to process.')

    args = parser.parse_args()

    loglevel = logging.INFO
    if args.quiet:
        loglevel = logging.WARNING
    elif args.debug:
        loglevel = logging.DEBUG

    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%dT%H:%M:%S', level=loglevel)
    logging.captureWarnings(True)
    logger = logging.getLogger(__name__)

    conf = helpers.config(args.config, args.resource)

    mapping = {}
    if 'sheet_name' in conf:
        mapping_data = pd.read_excel(conf['mapping_file'], sheet_name=conf['sheet_name'])
        for row in mapping_data.iterrows():
            mapping[row[1][conf['account_col']].lower()] = row[1][conf['project_col']].lower()

    if logger.isEnabledFor(logging.DEBUG):
        for m, v in mapping.items():
            logging.debug(f'{m} -> {v}')

    trnsl = None
    if args.resource in ['delta', 'deltaai']:
        trnsl = helpers.NcsaTranslator(mapping)
    elif args.resource == 'expanse':
        trnsl = helpers.SdscTranslator(mapping)

    for fullpath, filename in helpers.fileiterator(conf['source_dir'], conf['days'], conf['file_regex']):

        open_fn = gzip.open if filename.endswith('.gz') else open
        with open_fn(fullpath, 'rt', encoding='utf-8', errors='ignore') as filep:

            if filename.endswith('.json') or filename.endswith('.json.gz'):
                process_json(filep, fullpath, filename, conf['dest_dir'], trnsl)
            elif args.resource == 'anvil':
                process_anvil(filep, fullpath, filename, conf['dest_dir'], mapping)
            else:
                raise Exception('TODO')
