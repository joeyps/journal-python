import logging
import re
import time

RE_REMOVE_TAGS = re.compile(r"<[^>]+>")

def timing(f):
    def wrap(*args):
        time1 = time.time()
        ret = f(*args)
        time2 = time.time()
        logging.info('[perf] %s function took %0.3f ms' % (f.func_name, (time2-time1)*1000.0))
        return ret
    return wrap