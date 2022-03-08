from Cooper.GuidedMutation import CooperDataCollection
import os
import random
import zipfile
import xml.dom.minidom as minidom
import copy
from StringIO import StringIO

def P(p):
    return random.randint(0, 99) < p


class WordFile(object):
    def __init__(self, wordpath):
        self.subdict = {}
        with zipfile.ZipFile(wordpath, 'r') as zin:
            self.comment = zin.comment
            for item in zin.infolist():
                fn = item.filename
                content = zin.read(fn)
                self.subdict[fn] = content

    def writeword(self, outpath):
        outfd = open(outpath, 'wb')
        outfd.close()
        with zipfile.ZipFile(outpath, 'w') as zout:
            zout.comment = self.comment
            for item in self.subdict:
                zout.writestr(item, self.subdict[item])


word_cache = {}
def word_load(wordpath):
    if wordpath not in word_cache:
        word = WordFile(wordpath)
        if len(word_cache) > 20:
            del_key = random.choice(word_cache.keys())
            del word_cache[del_key]
        word_cache[wordpath] = word
    return copy.deepcopy(word_cache[wordpath])


def identifier_to_obj(doc, ident):
    obj = doc
    for idx in ident[1:]:
        obj = obj.childNodes[idx]
    return obj


def word_attribute_muation(fobj, ck, similar_objlist):
    attributes = {}
    for e in similar_objlist:
        o = e.attributes
        for k in o.keys():
            if k not in attributes:
                attributes[k] = []
            if o[k] not in attributes[k]:
                attributes[k].append(o[k])
    targetobj = fobj.childNodes[ck]
    can_add_names = list(set(attributes.keys()) - set(targetobj.attributes.keys()))
    if len(can_add_names) > 0:
        add_names = random.sample(can_add_names, min(random.randint(1, 3), len(can_add_names)))
        for name in add_names:
            value = random.choice(attributes[name])
            targetobj.attributes[name] = value
        return True
    else:
        return False


def word_whole_mutation(fobj, ck, similar_objlist):
    target_object = fobj.childNodes[ck]
    can_replace_objlist = [c for c in similar_objlist if set(c.attributes.keys()) != set(target_object.attributes.keys())]
    if len(can_replace_objlist) > 0:
        fobj.childNodes[ck] = random.choice(can_replace_objlist)
        return True
    elif len(similar_objlist) > 0:
        fobj.childNodes[ck] = random.choice(similar_objlist)
        return True
    else:
        return False


def word_universal_mutation(fobj, ck):
    target_object = fobj.childNodes[ck]
    for k in target_object.attributes.keys():
        v = target_object.attributes[k].nodeValue
        if P(30):
            newv = v*random.randint(2, 20)
        elif P(50) and str.isdigit(v.encode('utf-8')):
            num = int(v)
            newv = str(num+ random.randint(1, 1024) if P(50) else random.randint(-1024, -1))
        elif P(80):
            newv = ''.join([chr(random.randint(32, 127)) for _ in range(random.randint(1, 32))])
        else:
            newv = ''
        target_object.attributes[k] = newv
    return True


def word_native_mutation(word_dirpath, wordname, mut_list, cooper_data):
    # retrieve a few similar objects in the same class
    assert isinstance(cooper_data, CooperDataCollection)
    objcls_list = cooper_data.objcls_list
    clsidx_similar_objlist_map = {}
    for obj_identifier, clsidx in mut_list:
        clsidx_similar_objlist_map[clsidx] = []
    for clsidx in clsidx_similar_objlist_map.keys():
        cls = objcls_list[clsidx]
        can_similar_wordnames = list(set([c[0] for c in cls.refs]))
        incache_pdfnames = [c for c in can_similar_wordnames if os.path.join(word_dirpath, c) in word_cache.keys()]
        if len(incache_pdfnames) > 0 and P(90):
            can_similar_wordnames = incache_pdfnames
        sel_similar_pdfnames = random.sample(can_similar_wordnames, min(random.randint(1, 2), len(can_similar_wordnames)))
        for pname in sel_similar_pdfnames:
            worddata = word_load(os.path.join(word_dirpath, pname))
            doc = minidom.parseString(worddata.subdict['word/document.xml'])

            identifier_cidx_map = cooper_data.samplecls_map[pname]
            p_can_identifiers = [c for c in identifier_cidx_map.keys() if identifier_cidx_map[c] == clsidx]
            random.shuffle(p_can_identifiers)
            for ident in p_can_identifiers[:512]:
                similar_obj = identifier_to_obj(doc, ident)
                clsidx_similar_objlist_map[clsidx].append(similar_obj)

    # carry out mutation operation
    word = word_load(os.path.join(word_dirpath, wordname))
    doc = minidom.parseString(word.subdict['word/document.xml'])
    for identifier, clsidx in mut_list:
        fobj = doc
        ck = identifier[-1]
        if True:
        # try:
            for k in identifier[1:-1]:
                fobj = fobj.childNodes[k]
        # except:
        #     continue
        mutated = False
        if P(50):
            mutated = word_attribute_muation(fobj, ck, clsidx_similar_objlist_map[clsidx])
        if not mutated:
            mutated = word_whole_mutation(fobj, ck, clsidx_similar_objlist_map[clsidx])
        if P(30):
            mutated = word_universal_mutation(fobj, ck)
    buf = StringIO()
    doc.writexml(buf)
    newcontent = buf.getvalue().encode('utf-8')
    word.subdict['word/document.xml'] = newcontent
    return word
