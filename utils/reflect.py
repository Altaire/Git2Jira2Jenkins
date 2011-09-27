import pickle, gc, collections

rcount = 0
def reflect():
    global rcount
    if rcount % 10 == 0:
        counts = collections.defaultdict(int)
        examples = dict()
        for obj in gc.get_objects():
            counts[repr(type(obj))] += 1
            if repr(type(obj)) not in examples:
                examples[repr(type(obj))] = (repr(obj), str(obj.__dict__) if hasattr(obj, '__dict__') else None)
        pickle.dump(counts,
                    file('dump_%.2i.dump' % (rcount/10), 'w+'))
        pickle.dump(examples,
                    file('ex_%.2i.dump' % (rcount/10), 'w+'))
        print counts
    rcount += 1
