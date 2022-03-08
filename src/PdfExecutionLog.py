# -*- coding: gbk -*-
from win32gui import *
import win32gui
import win32con
from PdfPaser.pdf import PdfFileParser
from PdfPaser.generic import DictionaryObject, ArrayObject, NameObject, IndirectObject, DecodedStreamObject
import os
import time
import re
import cPickle as pickle


def pdf_append_object(pdf, obj):
    pdf._objects.append(obj)
    return IndirectObject(len(pdf._objects), 0, None)


def get_page_ids(pdf):
    root_id = pdf._root.idnum
    catalog = pdf._objects[root_id-1]
    obj_queue = [catalog['/Pages'].idnum]
    page_list = []
    pages_list = []
    i = 0
    while i < len(obj_queue):
        objid = obj_queue[i]
        obj = pdf._objects[objid-1]
        if '/Type' in obj and obj['/Type'] == '/Pages' or '/Kids' in obj:
            if objid not in pages_list:
                pages_list.append(objid)
                if '/Kids' in obj:
                    kids_arr = obj['/Kids']
                    while isinstance(kids_arr, IndirectObject):
                        kids_arr = pdf._objects[kids_arr.idnum-1]
                    if isinstance(kids_arr, ArrayObject):
                        for o in kids_arr:
                            if isinstance(o, IndirectObject) and o.idnum not in obj_queue:
                                obj_queue.append(o.idnum)
        else:
            if '/Type' in obj and obj['/Type'] == '/Page' and objid not in page_list:
                page_list.append(objid)
        i += 1
    return pages_list, page_list


def pdf_add_js(pdf, jscode):
    try:
        _, pageids = get_page_ids(pdf)
        firstpidx = pageids[0] - 1
        pageobj = pdf._objects[firstpidx]
        while isinstance(pageobj, IndirectObject):
            pageobj = pdf._objects[pageobj.idnum - 1]
        pageobj = pdf._objects[firstpidx]
        open_action = DictionaryObject()
        js_action = DictionaryObject()
        js_object = DecodedStreamObject()
        pageobj[NameObject('/AA')] = open_action
        open_action[NameObject('/O')] = js_action
        js_action[NameObject('/Type')] = NameObject('/Action')
        js_action[NameObject('/S')] = NameObject('/JavaScript')
        js_action[NameObject('/JS')] = pdf_append_object(pdf, js_object)
        js_object.setData(jscode)
    except:
        return False
    else:
        return True


def prepare_pdf_logcode(api_info):
    def value_checker(type, name):
        if type == 'array':
            return 'if((ret instanceof Array) && ret.length>0)'.format(name=name)
        elif type == 'object':
            return 'if(ret)'.format(
                name=name)
        elif type == 'number':
            return 'if(ret>0)'.format(
                name=name)
        else:
            assert False
    code = 'console.show();\r\nouts="info:";\r\n'
    for name, (exp, type) in api_info.items():
        if exp.find('<page_idx>') < 0:
            code += '''try{{
    var ret={exp};
    {checker}{{outs+="[{name}:yes]";}}else{{outs+="[{name}:no]";}}
}}catch(e){{
    outs+="[{name}:no]";
}}'''.format(exp=exp, name=name, checker=value_checker(type, name))
        else:
            code += '''try{{
    var appends="[{name}:no]";
    for(var pidx=0;pidx<=this.numPages;pidx++){{
        var ret = {exp};
        {checker}{{appends="[{name}:yes]";break;}}
    }}
    outs+=appends;
}}catch(e){{
    outs+="[{name}:no]";
}}
'''.format(exp=exp.replace('<page_idx>', 'pidx'), name=name, checker=value_checker(type, name))
    code += 'app.alert(outs);'
    return code


def get_child_windows(parent):
    if not parent:
        return
    hwndChildList = []
    win32gui.EnumChildWindows(parent, lambda hwnd, param: param.append(hwnd),  hwndChildList)
    return hwndChildList


def detect_loginfo(hwnd, mouse):
    global alertstring
    windowtext = GetWindowText(hwnd).decode('gbk')
    if windowtext.startswith('Warning: JavaScript Window'):
        cl = get_child_windows(hwnd)
        for c in cl:
            t = GetWindowText(c).decode('gbk')
            if t.startswith('info:'):
                alertstring = t[5:]
                break


alertstring = None
def execute_and_log_pdf(pdfpath, api_info):
    global alertstring
    tmpdir = 'temp'
    if not os.path.exists(tmpdir):
        os.mkdir(tmpdir)
    pdfname = os.path.basename(pdfpath)
    try:
        with open(pdfpath, 'rb') as infd:
            pdf = PdfFileParser(infd)
    except:
        return None
    logcode = prepare_pdf_logcode(api_info)
    try:
        pdf_add_js(pdf, logcode)
    except:
        print 'Error occurs when adding js code into {}'.format(pdfname)
        return None
    tmppath = os.path.join(tmpdir, 'tmp.pdf')
    with open(tmppath, 'wb') as outfd:
        pdf.write(outfd)
    acrord32_exe_path = 'C:\\\\Program Files (x86)\\\\Adobe\\\\Acrobat Reader DC\\\\Reader\\\\Acrord32.exe'
    cmd = 'start "" "{executable}" "{sample}"'.format(executable=acrord32_exe_path, sample=tmppath)
    for _ in range(3):
        os.system('taskkill /F /IM AcroRd32.exe')
        time.sleep(0.5)

    os.system(cmd)
    start_time = time.time()
    alertstring = None
    while True:
        EnumWindows(detect_loginfo, 0)
        if alertstring is not None or time.time()>start_time+15:
            break

    for _ in range(3):
        os.system('taskkill /F /IM AcroRd32.exe')
        time.sleep(0.5)

    logresult = {}
    if alertstring is not None:
        log_items = re.findall(r'\[.*?\]', alertstring)
        for item in log_items:
            item = item.strip('[]')
            k, v = item.split(':')
            logresult[k] = v
    return logresult


def handle_pdfrepo_forlog(pdf_dirpath, api_info):
    pdfpathlist = [os.path.join(pdf_dirpath, c) for c in os.listdir(pdf_dirpath) if c.endswith('.pdf')]
    logresult = {}
    for pdfpath in pdfpathlist:
        pdfname = os.path.basename(pdfpath)

        if True:
        # try:
            logdata = execute_and_log_pdf(pdfpath, api_info)
            if logdata is not None:
                logresult[pdfname] = logdata
        # except:
        #     print 'ERROR: log {} failed.'.format(pdfname)
        # else:
        #     print 'log {} success.'.format(pdfname)
        print 'Logging, {}/{}, {}'.format(pdfpathlist.index(pdfpath)+1, len(pdfpathlist), pdfname)
    reversed_api_logdata = {}
    for fname in logresult.keys():
        for apiname in logresult[fname].keys():
            if apiname not in reversed_api_logdata:
                reversed_api_logdata[apiname] = {}
            reversed_api_logdata[apiname][fname] = True if logresult[fname][apiname] == 'yes' else False
    return reversed_api_logdata


if __name__ == '__main__':
    pdfsamplerepo_path = 'PdfSamples'
    logresultdir_path = 'Logresult'
    if not os.path.exists(logresultdir_path):
        os.mkdir(logresultdir_path)
    # record_loginfo_pdf(pdfsamplerepo_path, logresultdir_path)