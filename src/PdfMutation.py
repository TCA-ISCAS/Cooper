from Cooper.GuidedMutation import CooperDataCollection
from PdfPaser.generic import DictionaryObject, ArrayObject, NameObject, ByteStringObject, TextStringObject, NumberObject, NullObject
from PdfPaser.pdf import PdfFileParser
import os
import random
import copy


def P(p):
    return random.randint(0, 99) < p


pdf_cache = {}
def pdf_load(pdfpath):
    if pdfpath not in pdf_cache:
        pdf = PdfFileParser(pdfpath)
        if len(pdf_cache) > 20:
            del_key = random.choice(pdf_cache.keys())
            del pdf_cache[del_key]
        pdf_cache[pdfpath] = pdf
    return copy.deepcopy(pdf_cache[pdfpath])


def identifier_to_obj(pdf, identifer):
    o = pdf._objects
    for k in identifer:
        o = o[k]
    return o


_interesting_integer = [-2, -1, 0, 1, 2, 8, 16, 256, 512, 1024, 4096, 65536]
_interesting_string_lens = [32, 64, 256, 1024, 4096, 8192]
_interesting_pdfobj = [DictionaryObject(), ArrayObject(), NullObject(), NameObject(), TextStringObject(), ByteStringObject()]


def string_mutation(v):
    if P(30):
        new_value = v.__class__(v * random.randint(2, 3))
    elif P(60):
        newlen = random.choice(_interesting_string_lens)
        if len(v) > 0:
            newstr = v * (newlen / len(v)) + v[:(newlen % len(v))]
            new_value = v.__class__(newstr)
        else:
            newstr = 'A' * newlen
            new_value = v.__class__(newstr)
    else:
        new_value = v.__class__('')
    return new_value


def num_mutation(v):
    if P(30):
        new_value = NumberObject(v * random.randint(2, 5))
    else:
        new_value = NumberObject(random.choice(_interesting_integer))
    return new_value


def dict_mutation(v):
    if len(v) > 0 and P(60):
        can_del_keys = v.keys()
        sel_del_keys = random.sample(can_del_keys, min(random.randint(1, 3), len(can_del_keys)))
        for k in sel_del_keys:
            del v[k]
        new_value = v
    else:
        new_value = random.choice(_interesting_pdfobj)
    return new_value


def arr_mutation(v):
    if len(v) > 0 and P(80):
        del_idxes = random.sample(range(len(v)), random.randint(1, len(v)))
        for idx in sorted(del_idxes, reverse=True):
            del v[idx]
        new_value = v
    else:
        new_value = random.choice(_interesting_pdfobj)
    return new_value


def other_mutation(v):
    return random.choice(_interesting_pdfobj)


def pdf_attribute_muation(fobj, ck, similar_objlist):
    attributes = {}
    for o in similar_objlist:
        for k in o:
            if k not in attributes:
                attributes[k] = []
            if o[k] not in attributes[k]:
                attributes[k].append(o[k])
    targetobj = fobj[ck]
    can_add_names = list(set(attributes.keys()) - set(targetobj.keys()))
    if len(can_add_names) > 0:
        add_names = random.sample(can_add_names, min(random.randint(1, 3), len(can_add_names)))
        for name in add_names:
            value = random.choice(attributes[name])
            targetobj[name] = value
        return True
    else:
        return False


def pdf_whole_mutation(fobj, ck, similar_objlist):
    target_object = fobj[ck]
    can_replace_objlist = [c for c in similar_objlist if set(c.keys()) != set(target_object.keys())]
    if len(can_replace_objlist)>0:
        fobj[ck] = random.choice(can_replace_objlist)
        return True
    elif len(similar_objlist)>0:
        fobj[ck] = random.choice(similar_objlist)
        return True
    else:
        return False


def pdf_universal_mutation(fobj, ck):
    mutated = False
    target_object = fobj[ck]
    can_keys = target_object.keys()
    sel_mut_keys = random.sample(can_keys, min(random.randint(1, 3), len(can_keys)))
    for k in sel_mut_keys:
        v = target_object[k]
        if isinstance(v, NameObject) or isinstance(v, TextStringObject) or isinstance(v, ByteStringObject):
            new_value = string_mutation(v)
        elif isinstance(v, NumberObject):
            new_value = num_mutation(v)
        elif isinstance(v, DictionaryObject):
            new_value = dict_mutation(v)
        elif isinstance(v, ArrayObject):
            new_value = arr_mutation(v)
        else:
            new_value = other_mutation(v)
        target_object[k] = new_value
        mutated = True
    return mutated


def pdf_native_mutation(pdf_dirpath, pdfname, mut_list, cooper_data, jscode):
    # retrieve a few similar objects in the same class
    assert isinstance(cooper_data, CooperDataCollection)
    objcls_list = cooper_data.objcls_list
    clsidx_similar_objlist_map = {}
    for obj_identifier, clsidx in mut_list:
        clsidx_similar_objlist_map[clsidx] = []
    for clsidx in clsidx_similar_objlist_map.keys():
        cls = objcls_list[clsidx]
        can_similar_pdfnames = list(set([c[0] for c in cls.refs]))
        incache_pdfnames = [c for c in can_similar_pdfnames if os.path.join(pdf_dirpath, c) in pdf_cache.keys()]
        if len(incache_pdfnames) > 0 and P(90):
            can_similar_pdfnames = incache_pdfnames
        sel_similar_pdfnames = random.sample(can_similar_pdfnames, min(random.randint(1, 2), len(can_similar_pdfnames)))
        for pname in sel_similar_pdfnames:
            pdfdata = pdf_load(os.path.join(pdf_dirpath, pname))

            identifier_cidx_map = cooper_data.samplecls_map[pname]
            p_can_identifiers = [c for c in identifier_cidx_map.keys() if identifier_cidx_map[c] == clsidx]
            for ident in p_can_identifiers:
                similar_obj = identifier_to_obj(pdfdata, ident)
                clsidx_similar_objlist_map[clsidx].append(similar_obj)

    # carry out mutation operation
    pdf = pdf_load(os.path.join(pdf_dirpath, pdfname))
    for identifier, clsidx in mut_list:
        fobj = pdf._objects
        ck = identifier[-1]
        try:
            for k in identifier[:-1]:
                fobj = fobj[k]
        except:
            continue
        mutated = False
        if P(50):
            mutated = pdf_attribute_muation(fobj, ck, clsidx_similar_objlist_map[clsidx])
        if not mutated:
            mutated = pdf_whole_mutation(fobj, ck, clsidx_similar_objlist_map[clsidx])
        if P(30):
            mutated = pdf_universal_mutation(fobj, ck)

    return pdf



