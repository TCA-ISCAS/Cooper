from Cooper.NativeCluster import ObjClass, AttributeSet, cooper_object_cluster
from Cooper.RelationshipInfer import cooper_infer_relatinship
from Cooper.GuidedMutation import cooper_guided_mutation, CooperDataCollection

from WordExecutionLog import handle_wordrepo_forlog, insert_vba_to_docx
from WordMutation import word_native_mutation, word_load
import StringIO
import os
import time
import shutil
import random
import sys
import cPickle as pickle
import zipfile
from xml.dom.minidom import parse, Text
import xml.dom.minidom
from grammar import Grammar


def word_objextractor(word_path):
    word_name = os.path.basename(word_path)
    doc_content = None
    with zipfile.ZipFile(word_path, 'r') as zin:
        for item in zin.infolist():
            fn = item.filename
            if fn == 'word/document.xml':
                doc_content = zin.read(fn)
    if doc_content is None:
        return None
    olist = []
    domtree = xml.dom.minidom.parseString(doc_content)
    nodequeue = [('root', domtree, (word_name, 0))]
    iii = 0
    while iii < len(nodequeue):
        leadkey, n, sk = nodequeue[iii]
        iii += 1
        if n.attributes is not None and len(n.attributes)>0:
            attrs = AttributeSet()
            for name in n.attributes.keys():
                value = n.attributes[name]
                attrs.add_attr(name, None)
            olist.append((leadkey, attrs, sk))
        for c_idx in range(len(n.childNodes)):
            child = n.childNodes[c_idx]
            if isinstance(child, Text):
                continue
            c_leadkey = child.tagName
            c_sk = sk + (c_idx, )
            nodequeue.append((c_leadkey, child, c_sk))
    return olist


def word_object_cluster(word_dirpath):
    objcls_list = cooper_object_cluster(word_dirpath, word_objextractor)
    return objcls_list


def word_obtain_logdata(pdf_dirpath, pdf_api_info):
    api_logdata = handle_wordrepo_forlog(pdf_dirpath, pdf_api_info)
    return api_logdata


def word_vba_generator(apiname):
    precode = '''
'''
    grammar = Grammar()
    grammar.parse_from_file('VbaTemplate/root.txt')
    code = grammar.generate_vba_scripts(apiname, 2000)
    return precode + code


def word_relationship_infer(objcls_list, api_logdata):
    api_relationship = {}
    for apiname in api_logdata.keys():
        this_rela = cooper_infer_relatinship(objcls_list, api_logdata[apiname])
        if this_rela is not None:
            api_relationship[apiname] = cooper_infer_relatinship(objcls_list, api_logdata[apiname])
    return api_relationship


def word_cooper_data_prepare(word_dirpath, mid_datapath):
    word_api_info = {
        'Paragraph': ('Paragraphs.Count', 'number'),
        'Pane': ('ActiveWindow.panes.Count', 'number'),
        'Field': ('fields.Count', 'number'),
        'Table': ('tables.Count', 'number'),
    }
    if not os.path.exists(mid_datapath):
        os.mkdir(mid_datapath)
    objcls_datapath = os.path.join(mid_datapath, 'word_objcls_list.pickle')
    api_logdata_datapath = os.path.join(mid_datapath, 'word_api_logdata.pickle')
    api_relationship_datapath = os.path.join(mid_datapath, 'word_api_relationship.pickle')

    # obtain object class list
    if not os.path.exists(objcls_datapath):
        print 'Preparing Object Class list.'
        objcls_list = word_object_cluster(word_dirpath)
        with open(objcls_datapath, 'wb') as outfd:
            pickle.dump(objcls_list, outfd)
        print 'Object Class List is ready.'
    else:
        with open(objcls_datapath, 'rb') as infd:
            objcls_list = pickle.load(infd)

    # obtain api_logdata
    if not os.path.exists(api_logdata_datapath):
        print 'Preparing Api logdata'
        api_logdata = word_obtain_logdata(word_dirpath, word_api_info)
        with open(api_logdata_datapath, 'wb') as outfd:
            pickle.dump(api_logdata, outfd)
        print 'Api logdata is ready'
    else:
        with open(api_logdata_datapath, 'rb') as infd:
            api_logdata = pickle.load(infd)

    # obtain api_relationship
    if not os.path.exists(api_relationship_datapath):
        print 'Preparing Api Relationship'
        api_relationship = word_relationship_infer(objcls_list, api_logdata)
        with open(api_relationship_datapath, 'wb') as outfd:
            pickle.dump(api_relationship, outfd)
        print 'Api Relationship is ready'
    else:
        with open(api_relationship_datapath, 'rb') as infd:
            api_relationship = pickle.load(infd)
    coopdata = CooperDataCollection(objcls_list, api_relationship, api_logdata)
    return coopdata


def word_input_generation(word_dirpath, cooper_data, script_generator, out_dirpath, want_cnt):
    assert isinstance(cooper_data, CooperDataCollection)
    generated_cnt = 0
    basedir = os.path.dirname(os.path.abspath(__file__))
    tmpdir = os.path.join(basedir, 'tmpdir')
    if not os.path.exists(tmpdir):
        os.mkdir(tmpdir)
    while True:
        mutation_info = cooper_guided_mutation(cooper_data)
        for apiname, pdfname, identifers in mutation_info:
            vbacode = script_generator(apiname)
            mutated_word = word_native_mutation(word_dirpath, pdfname, identifers, cooper_data)
            tmpdocx_path = os.path.join(tmpdir, 'tmp.docx')
            if os.path.exists(tmpdocx_path):
                os.remove(tmpdocx_path)
            mutated_word.writeword(tmpdocx_path)
            tmpvba_path = os.path.join(tmpdir, 'vba.txt')
            if os.path.exists(tmpvba_path):
                os.remove(tmpvba_path)
            with open(tmpvba_path, 'wb') as outfd:
                outfd.write(vbacode)
            output_name = time.strftime('%y_%m_%d_%H_%M_%S_{}.docm'.format(random.randint(0, 10000)))
            output_path = os.path.join(out_dirpath, output_name)
            insert_vba_to_docx(tmpdocx_path, tmpvba_path, output_path)
            print 'Successfully generate {}.'.format(output_name)

            generated_cnt += 1
            if generated_cnt >= want_cnt:
                break
        if generated_cnt >= want_cnt:
            break


def word_solution():
    try:
        word_dirpath = sys.argv[1]
        mid_datapath = sys.argv[2]
        word_outputpath = sys.argv[3]
        generate_num = int(sys.argv[4])
        if generate_num > 10000:
            generate_num = 10000
        if generate_num <= 0:
            generate_num = 20
    except:
        word_dirpath = 'WordSamples'
        mid_datapath = 'WordData'
        word_outputpath = 'WordInputs'
        generate_num = 500
    if not os.path.exists(word_dirpath):
        print 'ERROR: pdf samples directory "{}" not exists.'.format(word_dirpath)
        return
    if len(os.listdir(word_dirpath)) <= 100:
        print 'ERROR: pdf samples count smaller than 100, will exit'
        return
    if not os.path.exists(mid_datapath):
        os.mkdir(mid_datapath)
    if not os.path.exists(word_outputpath):
        os.mkdir(word_outputpath)
    cooper_data = word_cooper_data_prepare(word_dirpath, mid_datapath)
    word_input_generation(word_dirpath, cooper_data, word_vba_generator, word_outputpath, generate_num)


def main():
    word_solution()


def test():
    word_dirpath = 'WordSamples'
    wordnames = os.listdir(word_dirpath)
    sample_name = sorted(wordnames)[0]
    for sample_name in wordnames:
        sample_path = os.path.join(word_dirpath, sample_name)
        word_objextractor(sample_path)


def test1():
    vbacode = word_vba_generator('aaa')
    with open('vba.txt', 'wb') as outfd:
        outfd.write(vbacode)

def test2():
    allsamples = os.listdir('WordSamples')
    for i in range(100):
        samplepath = os.path.join('WordSamples', random.choice(allsamples))
        word_data = word_load(samplepath)
        outpath = os.path.join('WordInputs', '{}.docm'.format(i))
        word_data.writeword(outpath)
        print outpath


if __name__ == '__main__':
    main()