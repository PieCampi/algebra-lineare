#Prova per MATLAB
import sys

def bytes2human(n):
    symbols = ('K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')
    prefix = {}
    for i, s in enumerate(symbols):
        prefix[s] = 1 << (i + 1) * 10
    for s in reversed(symbols):
        if n >= prefix[s]:
            value = float(n) / prefix[s]
            return '%.1f%s' % (value, s)
    return "%sB" % n

if __name__ == '__main__':
    value_to_convert = float(3589634)
    x = bytes2human(value_to_convert)
    sys.stdout.write('%s' % x)