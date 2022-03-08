from PdfPaser.generic import DictionaryObject, ArrayObject, IndirectObject, NameObject, PdfObject
from PdfPaser.pdf import PdfFileParser
import cPickle as pickle
import os
from StringIO import StringIO


class ObjClass(object):
    def __init__(self, leadkey):
        self.leadkey = leadkey
        self.knum = {}  # record how many objects contain each key.
        self.refs = set()  # record all object's reference.

    def _high_key(self):
        return [c for c in self.knum.keys() if self.knum[c]*1.0/len(self.refs) >= 0.5]

    def add_obj(self, attrobj, ref):
        assert isinstance(attrobj, AttributeSet)
        for k, v in attrobj.attrs:
            if k not in self.knum:
                self.knum[k] = 0
            self.knum[k] += 1
        self.refs.add(ref)

    def objsim(self, attrobj):
        objks = set([c[0] for c in attrobj.attrs])
        hkeys = set(self._high_key())
        return 2.0*len(objks&hkeys)/(len(objks)+len(hkeys))

    def clssim(self, cls):
        assert isinstance(cls, ObjClass)
        hk0 = set(self._high_key())
        hk1 = set(cls._high_key())
        return 2.0*len(hk0 & hk1)/(len(hk0)+len(hk1))

    def merge(self, other):
        assert isinstance(other, ObjClass)
        leadkeys = set()
        for lk in (self.leadkey, other.leadkey):
            if isinstance(lk, tuple) or isinstance(lk, list) or isinstance(lk, set):
                leadkeys |= set(lk)
            else:
                leadkeys.add(lk)
        self.leadkey = leadkeys
        for k in other.knum:
            if k not in self.knum:
                self.knum[k] = 0
            self.knum[k] += other.knum[k]
        self.refs |= other.refs


class ObjCluster(object):
    def __init__(self):
        # for few samples, we use 4 for temporary threshold;
        # for large number of samples, reset to 64.
        self.good_threshold = 64
        self.step1_objclass = {}
        self.step2_objclass = []

    def cluster(self, sampledirpath, objextractor):
        self._cluster_step1(sampledirpath, objextractor)
        self._cluster_step2()
        pass

    def _cluster_step1(self, sampledirpath, objextractor):
        # 1st cluster step
        samplename_list = [c for c in os.listdir(sampledirpath)]
        for samplename in samplename_list:
            samplepath = os.path.join(sampledirpath, samplename)
            olist = objextractor(samplepath)
            if olist is None:
                print 'Warning, object extractor failed: {}'.format(samplename)
                continue
            for leadkey, attrobj, ref in olist:
                targetcls = None
                if leadkey not in self.step1_objclass:
                    self.step1_objclass[leadkey] = [ObjClass(leadkey)]
                    targetcls = self.step1_objclass[leadkey][-1]
                else:
                    maxscore, maxidx = 0, -1
                    for i in range(len(self.step1_objclass[leadkey])):
                        score = self.step1_objclass[leadkey][i].objsim(attrobj)
                        if score > maxscore:
                            maxscore, maxidx = score, i
                    if maxscore <= 0.4:
                        self.step1_objclass[leadkey].append(ObjClass(leadkey))
                        targetcls = self.step1_objclass[leadkey][-1]
                    else:
                        targetcls = self.step1_objclass[leadkey][maxidx]
                targetcls.add_obj(attrobj, ref)
            print 'Clustering, {}/{}, {}'.format(samplename_list.index(samplename)+1, len(samplename_list), samplename)

    def _cluster_step2(self):
        def get_root(i, f):
            j = f[i]
            while j != f[j]:
                j = f[j]
            return j
        # choose good clses with threshold
        goodclses = []
        for k in self.step1_objclass:
            for cls in self.step1_objclass[k]:
                if len(cls.refs) >= self.good_threshold:
                    goodclses.append(cls)
        # group classes
        fathers = {c: c for c in range(len(goodclses))}
        for i in range(len(goodclses)):
            fi = get_root(i, fathers)
            mi = goodclses[i]
            for j in range(i + 1, len(goodclses)):
                fj = get_root(j, fathers)
                mj = goodclses[j]
                if mi.clssim(mj) >= 0.7:
                    fathers[fj] = fi
        groups = {}
        for i in range(len(goodclses)):
            fi = get_root(i, fathers)
            if fi not in groups:
                groups[fi] = set()
            groups[fi].add(i)

        # merge classes in same group
        for fi in groups.keys():
            fmodel = goodclses[fi]
            if not isinstance(fmodel.leadkey, set):
                fmodel.leadkey = {fmodel.leadkey}
            for j in groups[fi]:
                if fi == j:
                    continue
                jmodel = goodclses[j]
                fmodel.merge(jmodel)
            self.step2_objclass.append(fmodel)


class AttributeSet(object):
    def __init__(self, _attrs=None):
        if _attrs is not None:
            assert isinstance(_attrs, dict)
            self.attrs = set(_attrs.items())
        else:
            self.attrs = set()

    def add_attr(self, name, value):
        self.attrs.add((name, value))


# Cooper's interface for object cluster
def cooper_object_cluster(sample_dirpath, sample_obj_extractor):
    """
    :param sample_dirpath: The absolute path for the sample repo.
    :param sample_obj_extractor: A function that extract attributes from sample
    :return: A list of ObjClass, which is the clustered object classes,
    this list will be used in relationship inference and cooperative mutation.
    """
    cluster = ObjCluster()
    cluster.cluster(sample_dirpath, sample_obj_extractor)
    final_objcls_list = cluster.step2_objclass
    return final_objcls_list


def main():
    pdfsamplerepo_path = 'E:\\pycharm-projects\\cooper\\massivepdfsamples'
    objcls_list = cooper_object_cluster(pdfsamplerepo_path, pdf_objextractor)
    with open('objcls_list.pickle', 'wb') as outfd:
        pickle.dump(objcls_list, outfd)
    a = 1


if __name__ == '__main__':
    main()