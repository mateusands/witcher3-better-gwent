#!/usr/bin/env python3
# Replays every sort case measured in the game (game/probes/scaleform.json) with candidate
# algorithms and reports how many cases each one reproduces exactly.
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'game', 'probes', 'scaleform.json')


def qsort_sliced(arr, less, threshold=9):
    """Scaleform Kernel Alg::QuickSortSliced (also shipped in Oculus LibOVR OVR_Alg.h)."""
    if len(arr) < 2:
        return
    stack = []
    base, limit = 0, len(arr)
    while True:
        ln = limit - base
        if ln > threshold:
            pivot = base + ln // 2
            arr[base], arr[pivot] = arr[pivot], arr[base]
            i, j = base + 1, limit - 1
            if less(arr[j], arr[i]):
                arr[j], arr[i] = arr[i], arr[j]
            if less(arr[base], arr[i]):
                arr[base], arr[i] = arr[i], arr[base]
            if less(arr[j], arr[base]):
                arr[j], arr[base] = arr[base], arr[j]
            while True:
                i += 1
                while less(arr[i], arr[base]):
                    i += 1
                j -= 1
                while less(arr[base], arr[j]):
                    j -= 1
                if i > j:
                    break
                arr[i], arr[j] = arr[j], arr[i]
            arr[base], arr[j] = arr[j], arr[base]
            if j - base > limit - i:
                stack.append((base, j))
                base = i
            else:
                stack.append((i, limit))
                limit = j
        else:
            j = base
            i = j + 1
            while i < limit:
                while less(arr[j + 1], arr[j]):
                    arr[j + 1], arr[j] = arr[j], arr[j + 1]
                    if j == base:
                        break
                    j -= 1
                j = i
                i += 1
            if stack:
                base, limit = stack.pop()
            else:
                break


CANDIDATES = {
    'QuickSortSliced(t=9)': lambda a, less: qsort_sliced(a, less, 9),
}


def main():
    cases = json.load(open(DATA))['sort']
    for name, fn in CANDIDATES.items():
        ok, bad = 0, []
        for c in cases:
            frac = c['case'].endswith('frac')
            keys = c['keys']
            items = [(k, i) for i, k in enumerate(keys)]
            if frac:
                less = lambda a, b: (a[0] - b[0]) * 0.25 < 0
            else:
                less = lambda a, b: (a[0] - b[0]) < 0
            fn(items, less)
            got = [i for _, i in items]
            if got == c['out']:
                ok += 1
            else:
                bad.append(c)
        print('%-28s %d/%d' % (name, ok, len(cases)))
        for c in bad[:3]:
            print('   miss', c['case'], c['keys'], '\n        game', c['out'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
