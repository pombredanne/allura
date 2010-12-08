import os.path
from glob import glob
from subprocess import Popen, PIPE
import sys

dir = os.path.abspath(os.path.dirname(__file__) + "/..")

def run(cmd):
    proc = Popen(cmd, shell=True, cwd=dir, stdout=PIPE, stderr=PIPE)
    # must capture & reprint stdount, so that nosetests can capture it
    (stdout, stderr) = proc.communicate()
    print stdout,
    print >>sys.stderr, stderr,
    return proc.returncode

find_py = "find Allura Forge* -name '*.py'"

def test_pyflakes():
    # skip some that aren't critical errors
    skips = [
        'imported but unused',
        'redefinition of unused',
        'assigned to but never used',
    ]
    if run(find_py + " | grep -v '/migrations/' | xargs pyflakes | grep -v '" + "' | grep -v '".join(skips) + "'") != 1:
        raise Exception('pyflakes failure')

def test_no_now():
    if run(find_py + " | xargs grep '\.now(' ") not in [1,123]:
        raise Exception("These should use .utcnow()")

def test_no_prints():
    skips = [
        '/tests/',
        'Allura/allura/command/',
        'Allura/ez_setup/',
        'Allura/push_re.py',
        'ForgeMail/forgemail/sstress.py',
    ]
    if run(find_py + " | grep -v '" + "' | grep -v '".join(skips) + "' | xargs grep -v '^ *#' | grep 'print ' | grep -E -v '(pprint|#pragma: ?printok)' ") != 1:
        raise Exception("These should use logging instead of print")

def test_no_tabs():
    if run(find_py + " | xargs grep '	' ") not in [1,123]:
        raise Exception('These should not use tab chars')