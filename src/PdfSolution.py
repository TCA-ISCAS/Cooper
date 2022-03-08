from Cooper.NativeCluster import ObjClass, AttributeSet, cooper_object_cluster
from Cooper.RelationshipInfer import cooper_infer_relatinship
from Cooper.GuidedMutation import cooper_guided_mutation, CooperDataCollection

from PdfExecutionLog import handle_pdfrepo_forlog, pdf_add_js
from PdfMutation import pdf_native_mutation

from grammar import Grammar
from PdfPaser.generic import DictionaryObject, ArrayObject, IndirectObject
from PdfPaser.pdf import PdfFileParser
import os
from StringIO import StringIO
import cPickle as pickle
import time
import random
import sys


def pdf_objextractor(pdfpath):
    def pdfobj2str(pobj):
        buf = StringIO()
        pobj.writeToStream(buf, None)
        return buf.getvalue()
    try:
        with open(pdfpath, 'rb') as infd:
            pdf = PdfFileParser(infd)
    except:
        return None
    pdfname = os.path.basename(pdfpath)
    olist = []
    handled_index = set()
    queue = [('root', pdf._objects[0], (pdfname, 0))]
    iii = 0
    while iii < len(queue):
        leadkey, obj, ref = queue[iii]
        iii += 1
        if isinstance(obj, DictionaryObject) and len(obj)>0:
            attrs = AttributeSet()
            for k in obj.keys():
                attrs.add_attr(pdfobj2str(k), None)  # Value is not used in cluster algorithm, just set None.
            olist.append((leadkey, attrs, ref))
        keys = None
        if isinstance(obj, DictionaryObject):
            keys = obj.keys()
        elif isinstance(obj, ArrayObject):
            keys = range(len(obj))
        if keys is not None:
            for k in keys:
                newleadkey = pdfobj2str(k) if not isinstance(k, int) else leadkey
                if isinstance(obj[k], IndirectObject):
                    objidx = obj[k].idnum-1
                    if objidx not in handled_index:
                        handled_index.add(objidx)
                        queue.append((newleadkey, pdf._objects[objidx], ref[:1]+(objidx, )))
                else:
                    queue.append((newleadkey, obj[k], ref+(k, )))
    return olist


def pdf_object_cluster(pdf_dirpath):
    objcls_list = cooper_object_cluster(pdf_dirpath, pdf_objextractor)
    return objcls_list


def pdf_obtain_logdata(pdf_dirpath, pdf_api_info):
    api_logdata = handle_pdfrepo_forlog(pdf_dirpath, pdf_api_info)
    return api_logdata


def pdf_relationship_infer(objcls_list, api_logdata):
    api_relationship = {}
    for apiname in api_logdata.keys():
        this_rela = cooper_infer_relatinship(objcls_list, api_logdata[apiname])
        if this_rela is not None:
            api_relationship[apiname] = cooper_infer_relatinship(objcls_list, api_logdata[apiname])
    return api_relationship


def pdf_cooper_data_prepare(pdf_dirpath, pdf_datapath):
    pdf_api_info = {
        'Annotation': ('this.getAnnots()', 'array'),
        'dataObjects': ('this.dataObjects', 'array'),
        'xfaform': ('this.dynamicXFAForm', 'object'),
        'sounds': ('this.sounds', 'array'),
        'icons': ('this.icons', 'array'),
        'numTemplates': ('this.numTemplates', 'number'),
        'Templates': ('this.templates', 'array'),
        'RichMedia': ('this.getAnnotsRichMedia(<page_idx>)', 'array'),
        'Annot3D': ('this.getAnnots3D(<page_idx>)', 'array'),
        'Field': ('this.numFields', 'number'),
        'OCGS': ('this.getOCGs()', 'array'),
    }
    if not os.path.exists(pdf_datapath):
        os.mkdir(pdf_datapath)
    objcls_datapath = os.path.join(pdf_datapath, 'pdf_objcls_list.pickle')
    api_logdata_datapath = os.path.join(pdf_datapath, 'pdf_api_logdata.pickle')
    api_relationship_datapath = os.path.join(pdf_datapath, 'pdf_api_relationship.pickle')

    # obtain object class list
    if not os.path.exists(objcls_datapath):
        print 'Preparing Object Class list.'
        objcls_list = pdf_object_cluster(pdf_dirpath)
        with open(objcls_datapath, 'wb') as outfd:
            pickle.dump(objcls_list, outfd)
        print 'Object Class List is ready.'
    else:
        with open(objcls_datapath, 'rb') as infd:
            objcls_list = pickle.load(infd)

    # obtain api_logdata
    if not os.path.exists(api_logdata_datapath):
        print 'Preparing Api logdata'
        api_logdata = pdf_obtain_logdata(pdf_dirpath, pdf_api_info)
        with open(api_logdata_datapath, 'wb') as outfd:
            pickle.dump(api_logdata, outfd)
        print 'Api logdata is ready'
    else:
        with open(api_logdata_datapath, 'rb') as infd:
            api_logdata = pickle.load(infd)


    # obtain api_relationship
    if not os.path.exists(api_relationship_datapath):
        print 'Preparing Api Relationship'
        api_relationship = pdf_relationship_infer(objcls_list, api_logdata)
        with open(api_relationship_datapath, 'wb') as outfd:
            pickle.dump(api_relationship, outfd)
        print 'Api Relationship is ready'
    else:
        with open(api_relationship_datapath, 'rb') as infd:
            api_relationship = pickle.load(infd)
    coopdata = CooperDataCollection(objcls_list, api_relationship, api_logdata)
    return coopdata


def pdf_input_generation(pdf_dirpath, cooper_data, script_generator, out_dirpath, want_cnt):
    """
    :param pdf_dirpath: A string representing the absolute path for pdf directory.
    :param objcls_list: A sequence of ObjClass generated by cooper.
    :param api_relationship: A two-level dict, api name -> object class index -> connective-value, representing
    the strength of the connection between api group and object class.
    :param api_logdata: A two-level dict, api name -> sample name -> boolean, representing
    whether the api executed successfully in the sample.
    :param script_generator: A function, that take api name for argument, and generate testing code.
    :return: A string which is the content of generated input.
    """
    assert isinstance(cooper_data, CooperDataCollection)
    generated_cnt = 0
    while True:
        mutation_info = cooper_guided_mutation(cooper_data)
        for apiname, pdfname, identifers in mutation_info:
            jscode = script_generator(apiname)
            mutated_pdf = pdf_native_mutation(pdf_dirpath, pdfname, identifers, cooper_data, jscode)
            if not pdf_add_js(mutated_pdf, jscode):
                print 'ERROR: when add js code.'
            output_name = time.strftime('%y_%m_%d_%H_%M_%S_{}.pdf'.format(random.randint(0, 10000)))
            output_path = os.path.join(out_dirpath, output_name)
            with open(output_path, 'wb') as outfd:
                mutated_pdf.write(outfd)
            print 'Successfully generate {}.'.format(output_name)

            generated_cnt += 1
            if generated_cnt >= want_cnt:
                break
        if generated_cnt >= want_cnt:
            break


def pdf_js_generator(apiname):
    pre_code = '''function GetVariable(fuzzervars, var_type) { if(fuzzervars[var_type]) { return fuzzervars[var_type]; } else { return null; }}
function SetVariable(fuzzervars, var_name, var_type) { fuzzervars[var_type] = var_name; }
fuzzervars={};
console.show();

'''
    grammar = Grammar()
    grammar.parse_from_file(os.path.join('PdfJsTemplate', 'root.txt'))
    code = grammar.generate_scripts(apiname, 2000)
    return pre_code + code


def pdf_solution():
    try:
        pdf_dirpath = sys.argv[1]
        pdf_datapath = sys.argv[2]
        pdf_outputpath = sys.argv[3]
        generate_num = int(sys.argv[4])
        if generate_num > 10000:
            generate_num = 10000
        if generate_num <= 0:
            generate_num = 20
    except:
        pdf_dirpath = 'PdfSamples'
        pdf_datapath = 'PdfData'
        pdf_outputpath = 'PdfInputs'
        generate_num = 20
    if not os.path.exists(pdf_dirpath):
        print 'ERROR: pdf samples directory "{}" not exists.'.format(pdf_dirpath)
        return
    if len(os.listdir(pdf_dirpath)) <= 100:
        print 'ERROR: pdf samples count smaller than 100, will exit'
        return
    if not os.path.exists(pdf_datapath):
        os.mkdir(pdf_datapath)
    if not os.path.exists(pdf_outputpath):
        os.mkdir(pdf_outputpath)
    cooper_data = pdf_cooper_data_prepare(pdf_dirpath, pdf_datapath)
    pdf_input_generation(pdf_dirpath, cooper_data, pdf_js_generator, pdf_outputpath, generate_num)


def main():
    pdf_solution()


if __name__ == '__main__':
    main()