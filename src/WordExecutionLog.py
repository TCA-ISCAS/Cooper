# -*- coding: gbk -*-
from win32gui import *
import win32gui
import win32con
import os
import re
import time
from StringIO import StringIO
import zipfile
import xml.dom.minidom as minidom
from xml.dom.minidom import Document, Element
from win32com.client import Dispatch


base_dir = os.path.dirname(os.path.abspath(__file__))
vbatemp_path = os.path.join(base_dir, 'VbaTemplate', 'a.docm')
docmwithvba_path = os.path.join(base_dir, 'VbaTemplate', 'b.docm')


def new_xmlnode(tagname, attrdicts):
    e = Element(tagname)
    for k, v in attrdicts.items():
        e.setAttribute(k, v)
    return e


def get_rels_allids(rels_doc):
    allids = set()
    relses = rels_doc.childNodes[0]
    for rel in relses.childNodes:
        if 'Id' in rel.attributes._attrs:
            allids.add(rel.attributes['Id'].value)
    return allids


class OfficeFile(object):
    def __init__(self, srcpath):
        self.subdict = {}
        with zipfile.ZipFile(srcpath, 'r') as zin:
            self.comment = zin.comment
            for item in zin.infolist():
                fn = item.filename
                content = zin.read(fn)
                try:
                    self.subdict[fn] = minidom.parseString(content)
                except:
                    self.subdict[fn] = content

    def _add_rel(self, dirname, owner, relnode):
        reles_item = '{}/_rels/{}.rels'.format(dirname, owner)
        reles_node = self.subdict[reles_item].childNodes[0]
        reles_node.appendChild(relnode)
        print 'a'

    def _add_contenttype(self, ctnodes):
        ctitem = '[Content_Types].xml'
        ctes_node = self.subdict[ctitem].childNodes[0]
        for ctn in ctnodes:
            childidx = 0
            while childidx < len(ctes_node.childNodes):
                childnode = ctes_node.childNodes[childidx]
                if childnode.hasAttribute('Extension') and ctn.hasAttribute('Extension'):
                    if childnode.getAttribute('Extension') == ctn.getAttribute('Extension'):
                        break
                if childnode.hasAttribute('PartName') and ctn.hasAttribute('PartName'):
                    if childnode.getAttribute('PartName') == ctn.getAttribute('PartName'):
                        break
                childidx += 1
            if childidx < len(ctes_node.childNodes):
                ctes_node.childNodes[childidx] = ctn
            else:
                ctes_node.appendChild(ctn)

    def add_vbascripts(self, vbadata):
        add_items = ['word/vbaData.xml', 'word/vbaProject.bin', 'word/_rels/vbaProject.bin.rels']
        for item in add_items:
            assert item in vbadata
            self.subdict[item] = vbadata[item]
        # modify some items
        # word/_rels/document.xml.rels
        item = 'word/_rels/document.xml.rels'
        allrids = get_rels_allids(self.subdict[item])
        newrid = 1
        while True:
            newrid_str = 'rId{}'.format(str(newrid))
            if newrid_str not in allrids:
                break
            newrid += 1
        vba_rel = new_xmlnode('Relationship', {
            'Id': newrid_str,
            'Target': 'vbaProject.bin',
            'Type': 'http://schemas.microsoft.com/office/2006/relationships/vbaProject'
        })
        self._add_rel('word', 'document.xml', vba_rel)

        # [Content_Types].xml
        vbaproj_ct = new_xmlnode('Default', {
            'ContentType': 'application/vnd.ms-office.vbaProject',
            'Extension': 'bin'
        })
        main_ct = new_xmlnode('Override', {
            'ContentType': 'application/vnd.ms-word.document.macroEnabled.main+xml',
            'PartName': '/word/document.xml'
        })
        vbadata_ct = new_xmlnode('Override', {
            'ContentType': 'application/vnd.ms-word.vbaData+xml',
            'PartName': '/word/vbaData.xml'
        })
        self._add_contenttype([vbaproj_ct, main_ct, vbadata_ct])

    def output(self, outpath):
        outfd = open(outpath, 'wb')
        outfd.close()
        with zipfile.ZipFile(outpath, 'w') as zout:
            zout.comment = self.comment
            for item in self.subdict:
                if isinstance(self.subdict[item], str):
                    zout.writestr(item, self.subdict[item])
                elif isinstance(self.subdict[item], Document):
                    bufferio = StringIO()
                    self.subdict[item].writexml(bufferio)
                    content = bufferio.getvalue().encode('utf-8')
                    zout.writestr(item, content)
                else:
                    assert None

def extract_vba_data(mpath):
    subdict = {}
    with zipfile.ZipFile(mpath, 'r') as zin:
        for item in zin.infolist():
            fn = item.filename
            content = zin.read(fn)
            subdict[fn] = content
    vba_items = ['word/vbaData.xml', 'word/vbaProject.bin', 'word/_rels/vbaProject.bin.rels']
    vba_data = {c: subdict[c] for c in vba_items}
    return vba_data

def combine_docx_and_docm(xpath, mpath, outpath):
    xfile = OfficeFile(xpath)
    vba_data = extract_vba_data(mpath)
    xfile.add_vbascripts(vba_data)
    xfile.output(outpath)


def insert_vba(temppath, vbacodepath, docmpath):
    app = Dispatch('Word.Application')
    app.Visible = True
    doc = app.Documents.Open(temppath)
    e = doc.VBProject.VBComponents[0].CodeModule.AddFromFile(vbacodepath)
    doc.SaveAs2(docmpath)
    doc.Close()
    app.Quit()


def insert_vba_to_docx(docx_path, vbacode_path, outpath):
    if os.path.exists(docmwithvba_path):
        os.remove(docmwithvba_path)
    insert_vba(vbatemp_path, vbacode_path, docmwithvba_path)
    if os.path.exists(docmwithvba_path):
        if os.path.exists(outpath):
            os.remove(outpath)
        combine_docx_and_docm(docx_path, docmwithvba_path, outpath)
        os.remove(docmwithvba_path)
        if os.path.exists(outpath):
            return True
    return False


def prepare_word_logcode(api_info):
    def value_checker(type, name):
        if type == 'number':
            return 'If ret > 0 '
    code = 'Private Sub Document_Open()\r\nOn Error Resume Next\r\nouts="info:"\r\n'
    for name, (exp, type) in api_info.items():
        code += 'ret={exp}\r\n{checker} Then outs = outs + "[{name}:yes]" Else outs = outs + "[{name}:no]":' \
                ' If Err.Number <> 0 Then outs = outs + "[{name}:no]"\r\n'.format(exp=exp, checker=value_checker(type, name), name=name)
    code += "MsgBox outs\r\nEnd Sub\r\n"
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
    if windowtext.startswith('Microsoft Word'):
        cl = get_child_windows(hwnd)
        for c in cl:
            t = GetWindowText(c).decode('gbk')
            if t.startswith('info:'):
                alertstring = t[5:]
                break

alertstring = None
def execute_and_log_word(wordpath, api_info):
    global alertstring
    tmpdir = os.path.join(base_dir, 'temp')
    if not os.path.exists(tmpdir):
        os.mkdir(tmpdir)

    logcode = prepare_word_logcode(api_info)
    logcode_path = os.path.join(tmpdir, 'vba.txt')
    docm_path = os.path.join(tmpdir, 'tmp.docm')
    with open(logcode_path, 'wb') as outfd:
        outfd.write(logcode)
    # if True:
    try:
        insert_vba_to_docx(wordpath, logcode_path, docm_path)
    except:
        print 'Error occurs when adding js code into {}'.format(wordpath)
        return None

    word_exe_path = 'C:\\Program Files\\Microsoft Office\\Office16\\WINWORD.EXE'
    cmd = 'start "" "{executable}" "{sample}"'.format(executable=word_exe_path, sample=docm_path)
    for _ in range(3):
        os.system('taskkill /F /IM winword.exe')
        time.sleep(0.5)

    os.system(cmd)
    start_time = time.time()
    alertstring = None
    while True:
        EnumWindows(detect_loginfo, 0)
        if alertstring is not None or time.time()>start_time+15:
            break

    for _ in range(3):
        os.system('taskkill /F /IM winword.exe')
        time.sleep(0.5)

    logresult = {}
    if alertstring is not None:
        log_items = re.findall(r'\[.*?\]', alertstring)
        for item in log_items:
            item = item.strip('[]')
            k, v = item.split(':')
            logresult[k] = v
    return logresult


def handle_wordrepo_forlog(word_dirpath, api_info):
    wordpathlist = [os.path.join(word_dirpath, c) for c in os.listdir(word_dirpath) if c.endswith('.docx')]
    logresult = {}
    errnum = 0
    for wordpath in wordpathlist:
        wordname = os.path.basename(wordpath)

        if True:
        # try:
            logdata = execute_and_log_word(wordpath, api_info)
            if logdata is not None:
                logresult[wordname] = logdata
                errnum = 0
            else:
                print 'log {} failed.'.format(wordname)
                errnum += 1
                if errnum > 5:
                    print '5 Errors when add execute_and_log.'
                    exit(0)
        # except:
        #     print 'ERROR: log {} failed.'.format(pdfname)
        # else:
        #     print 'log {} success.'.format(pdfname)
        print 'Logging, {}/{}, {}.'.format(wordpathlist.index(wordpath)+1, len(wordpathlist), wordname)
    reversed_api_logdata = {}
    for fname in logresult.keys():
        for apiname in logresult[fname].keys():
            if apiname not in reversed_api_logdata:
                reversed_api_logdata[apiname] = {}
            reversed_api_logdata[apiname][fname] = True if logresult[fname][apiname] == 'yes' else False
    return reversed_api_logdata
