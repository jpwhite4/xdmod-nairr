""" Helper functions """
import os
import re
import json
import datetime
import logging


def config(confpath, resource):

    combined = {}
    with open(confpath, 'r', encoding='utf-8', errors='ignore') as filep:
        conf = json.load(filep)
        for c,v in conf.items():
            if c != 'resources':
                combined[c] = v

        for c,v in conf['resources'][resource].items():
            combined[c] = v
    
    return combined

def fileiterator(prefix, age_days, fileregex):
    filenames = [x for x in os.listdir(prefix)]
    filenames.sort()

    now = datetime.datetime.now()

    freg = re.compile(fileregex)

    for filename in filenames:
        mtch = freg.match(filename)
        if not mtch:
            logging.debug(f'Skipping file with unrecognized name "{filename}".')
            continue
        try:
            fdate = datetime.datetime.strptime(mtch.group(1) + '-' + mtch.group(2) + '-' + mtch.group(3), '%Y-%m-%d')
            if now - fdate > datetime.timedelta(days=age_days):
                logging.debug('Skip %s due to time range', filename)
                continue
        except ValueError:
            logging.warning(f'Skip due to syntax error in datestamp in file "{filename}"')
            continue

        fullpath = os.path.join(prefix, filename)
        if os.path.isfile(fullpath):
            yield (fullpath, filename)
