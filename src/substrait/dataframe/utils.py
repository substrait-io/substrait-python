
def merge_extensions(*extensions):
    ret = {}
    for e in extensions:
        for k, v in e.items():
            if k not in ret:
                ret[k] = {}

            for k1, v1 in v.items():
                ret[k][k1] = v1

    return ret