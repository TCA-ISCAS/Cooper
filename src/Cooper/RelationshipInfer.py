import os
import cPickle as pickle
from NativeCluster import ObjClass


def cooper_infer_relatinship(objcls_list, logdata_dict):
    """
    :param objcls_list: a list, the object class list clustered by Cooper.
    :param logdata_dict: a dict,  {sample name: True/False}, indicate whether one api
    successfully executed in each sample.
    :return: a dict, {class idx: relation}, relation represent the strength of connection
    between this object class and api group.
    """
    succ_ns = set([c for c in logdata_dict.keys() if logdata_dict[c]])
    fail_ns = set([c for c in logdata_dict.keys() if not logdata_dict[c]])
    if len(succ_ns) == 0 or len(fail_ns) == 0:
        return None
    relationship_map = {}
    for clsidx in range(len(objcls_list)):
        cls = objcls_list[clsidx]
        cls_ns = set([ref[0] for ref in cls.refs])  # the first element of ref must be sample name.
        rate_s = len(succ_ns & cls_ns)*1.0/len(succ_ns)
        rate_f = len(fail_ns & cls_ns)*1.0/len(fail_ns)
        relationship_map[clsidx] = rate_s - rate_f
    return relationship_map


def main():
    annot_log_path = 'tmp_data\\example_Annotation_jslog.pickle'
    field_log_path = 'tmp_data\\example_Field_jslog.pickle'
    objcls_list_path = 'tmp_data\\example_objcls.pickle'
    with open(annot_log_path, 'rb') as infd:
        annotdata = pickle.load(infd)
    with open(field_log_path, 'rb') as infd:
        fielddata = pickle.load(infd)
    with open(objcls_list_path, 'rb') as infd:
        objcls_list = pickle.load(infd)
    annot_relationship_map = cooper_infer_relatinship(objcls_list, annotdata)
    field_relationship_map = cooper_infer_relatinship(objcls_list, fielddata)
    a = 1


if __name__ == '__main__':
    main()


#
# class ObjModel(object):
#     def __init__(self, leadkey):
#         self.leadkey = leadkey
#         self.keys = {}  # keys:num
#         self.knum = {}  # k:num
#         self.keyvalue={}
#         self.refs = set()
#
#     def combine(self, other):
#         assert isinstance(other, ObjModel)
#         leadkeys = set()
#         for lk in (self.leadkey, other.leadkey):
#             if isinstance(lk, tuple) or isinstance(lk, list) or isinstance(lk, set):
#                 leadkeys |= set(lk)
#             else:
#                 leadkeys.add(lk)
#         self.leadkey = leadkeys
#         for k in other.knum:
#             if k not in self.knum:
#                 self.knum[k] = 0
#             self.knum[k] += other.knum[k]
#         self.refs |= other.refs
#
#
#     def _high_key(self):
#         return [c for c in self.knum.keys() if self.knum[c]*1.0/len(self.refs) >= 0.5]
#
#     def add_obj(self, obj, serk):
#         if isinstance(obj, DictionaryObject):
#             ks = frozenset(obj.keys())
#             for k in ks:
#                 if k not in self.knum:
#                     self.knum[k] = 0
#                 self.knum[k] += 1
#             self.refs.add(serk)
#
#     def add_obj__(self, obj, serk):
#         if isinstance(obj, DictionaryObject):
#             ks = frozenset(obj.keys())
#             if ks not in self.keys:
#                 self.keys[ks] = 0
#             self.keys[ks] += 1
#             for k in ks:
#                 if k not in self.knum:
#                     self.knum[k] = 0
#                 self.knum[k] += 1
#                 v = obj[k]
#                 if isinstance(v, NameObject):
#                     if k not in self.keyvalue:
#                         self.keyvalue[k] = {}
#                     if v not in self.keyvalue[k]:
#                         self.keyvalue[k][v] = 0
#                     self.keyvalue[k][v] += 1
#         self.refs.add(serk)
#
#     def objsim(self, obj):
#         objks = set(obj.keys())
#         hkeys = set(self._high_key())
#         return 2.0*len(objks&hkeys)/(len(objks)+len(hkeys))
#
#     def modelsim(self, model):
#         assert isinstance(model, ObjModel)
#         hk0 = set(self._high_key())
#         hk1 = set(model._high_key())
#         return 2.0*len(hk0 & hk1)/(len(hk0)+len(hk1))
#
#     def objsim___(self, obj):
#         objks = obj.keys()
#         return 1.0*len(set(self.knum.keys())&set(objks))/min(len(objks), len(self.knum.keys()))
#
#     def objsim__(self, obj):
#         score = 0
#         objks = frozenset(obj.keys())
#         for ks in self.keys:
#             score += self.keys[ks]*2.0*len(objks&ks)/(len(ks)+len(objks))
#         score /= sum(self.keys.values())
#         return score
#
#     def modelsim__(self, model):
#         score = 0
#         cnt = 0
#         for objks in model.keys:
#             for ks in self.keys:
#                 score += self.keys[ks] * model.keys[objks] * 2.0 * len(objks & ks) / (len(ks) + len(objks))
#                 cnt += self.keys[ks] * model.keys[objks]
#         score /= cnt
#         return score


# def convert_model_data():
#     model_data_path = 'tmp_data\\models2.pickle'
#     objcls_list_path = 'tmp_data\\example_objcls.pickle'
#     with open(model_data_path, 'rb') as infd:
#         model_list = pickle.load(infd)
#     objcls_list = []
#     for model in model_list:
#         assert isinstance(model, ObjModel)
#         cls = ObjClass(model.leadkey)
#         cls.knum = model.knum
#         cls.refs = model.refs
#         objcls_list.append(cls)
#     with open(objcls_list_path, 'wb') as outfd:
#         pickle.dump(objcls_list, outfd)

# class Info(object):
#     def __init__(self, name):
#         self.name = name
#         if os.path.exists('{}_info.pickle'.format(self.name)):
#             with open('{}_info.pickle'.format(self.name), 'rb') as infd:
#                 old = pickle.load(infd)
#                 self.pdf_info = old.pdf_info
#         else:
#             self.pdf_info = {}
#
#     def add_info(self, pdfname, info):
#         self.pdf_info[pdfname] = info
#
#     def output(self):
#         with open('{}_info.pickle'.format(self.name), 'wb') as outfd:
#             pickle.dump(self, outfd)
#         with open('{}_info.txt'.format(self.name), 'wb') as outfd:
#             for pdfname in self.pdf_info:
#                 outfd.write('{}:{}\r\n'.format(pdfname, self.pdf_info[pdfname]))


#
#
# def covert_data():
#     old_path = 'tmp_data\\adobe_info.pickle'
#     new_path = 'tmp_data\\example_jslog.pickle'
#     annot_data_path = 'tmp_data\\example_Annotation_jslog.pickle'
#     field_data_path = 'tmp_data\\example_Field_jslog.pickle'
#     with open(old_path, 'rb') as infd:
#         data = pickle.load(infd)
#     outdata = {}
#     annotdata = {}
#     fielddata = {}
#     for fname in data.pdf_info.keys():
#         info = data.pdf_info[fname]
#         if info is None:
#             continue
#         outdata[fname] = {'Annotation': info['get_annots'], 'Field': info['numFields']}
#         annotdata[fname] = True if outdata[fname]['Annotation'] == 'yes' else False
#         fielddata[fname] = True if outdata[fname]['Field'] == 'yes' else False
#     with open(new_path, 'wb') as outfd:
#         pickle.dump(outdata, outfd)
#     with open(annot_data_path, 'wb') as outfd:
#         pickle.dump(annotdata, outfd)
#     with open(field_data_path, 'wb') as outfd:
#         pickle.dump(fielddata, outfd)
#     a = 1