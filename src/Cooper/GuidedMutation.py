import random
from NativeCluster import ObjClass


class CooperDataCollection(object):
    def __init__(self, objcls_list, api_relationship, api_logdata):
        self.objcls_list = objcls_list
        self.samplecls_map = convert_objcls_list_to_samplecls_map(objcls_list)
        self.api_relationship = api_relationship
        self.api_logdata = api_logdata


def convert_objcls_list_to_samplecls_map(objcls_list):
    # construct a two-level dict sample name -> object identifier -> object class index
    samplecls_map = {}
    for clsidx in range(len(objcls_list)):
        cls = objcls_list[clsidx]
        assert isinstance(cls, ObjClass)
        for ref in cls.refs:
            samplename = ref[0]
            objidentifier = ref[1:]
            if samplename not in samplecls_map:
                samplecls_map[samplename] = {}
            samplecls_map[samplename][objidentifier] = clsidx
    return samplecls_map


def select_cls(s_clsidx_set, relationship, sel_cnt):
    # calculate cls score
    rel_list = [(c, relationship[c]) for c in relationship.keys()]
    sorted_rel_list = sorted(rel_list, key=lambda c: c[1])
    cls_score_map = {sorted_rel_list[c][0]: c+1 for c in range(len(sorted_rel_list))}

    # select cls
    s_clsidx_list = list(s_clsidx_set)
    s_cls_ratio_list = [(c, cls_score_map[c]) for c in s_clsidx_list]
    ratio_sum = sum([c[1] for c in s_cls_ratio_list])
    selected_clsidxes = set()
    for _ in range(sel_cnt):
        r_value = random.randint(0, ratio_sum-1)
        acc = 0
        sel_clsidx = None
        for i in range(len(s_cls_ratio_list)):
            acc += s_cls_ratio_list[i][1]
            if acc > r_value:
                sel_clsidx = s_cls_ratio_list[i][0]
                break
        if sel_clsidx is not None:
            selected_clsidxes.add(sel_clsidx)
    return selected_clsidxes


def cooper_guided_mutation(cooper_data):
    samplecls_map, api_relationship, api_logdata = cooper_data.samplecls_map, cooper_data.api_relationship, cooper_data.api_logdata
    max_cnt = 10
    cooperative_info = []
    api_name_list = api_relationship.keys()
    random.shuffle(api_name_list)
    for api_name in api_name_list:
        relationship = api_relationship[api_name]
        can_sample_namelist = [c for c in api_logdata[api_name].keys() if api_logdata[api_name][c]]
        random.shuffle(can_sample_namelist)
        can_sample_namelist = can_sample_namelist[:3]

        for samplename in can_sample_namelist:
            objid_cls_map = samplecls_map[samplename]

            clsidx_set = set(objid_cls_map.values())
            selected_clsidx_set = select_cls(clsidx_set, relationship, random.randint(1, 3))

            can_objid_list = [(objid, objid_cls_map[objid]) for objid in objid_cls_map.keys() if objid_cls_map[objid] in selected_clsidx_set]
            o_cnt = min(random.randint(1, 3), len(can_objid_list))
            selected_objid = random.sample(can_objid_list, o_cnt)

            cooperative_info.append((api_name, samplename, selected_objid))
            if len(cooperative_info) > max_cnt:
                break
        if len(cooperative_info) > max_cnt:
            break
    return cooperative_info
