# Copyright (c) 2006, Mathieu Fenniak
# Copyright (c) 2007, Ashish Kulkarni <kulkarni.ashish@gmail.com>
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# * The name of the author may not be used to endorse or promote products
# derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import struct
import StringIO
import utils
import warnings
import sys
import copy
from hashlib import md5
from generic import DictionaryObject, NameObject, readObject, NullObject, IndirectObject, NumberObject, BooleanObject, ByteStringObject, TextStringObject, StreamObject, createStringObject, ArrayObject
from utils import readNonWhitespace, readUntilWhitespace
from addon import NotFoundObject


class PdfFileParser(object):
    def __init__(self, stream):
        if hasattr(stream, 'mode') and 'b' not in stream.mode:
            warnings.warn("PdfFileReader stream/file object is not in binary mode. It may not be read correctly.", utils.PdfReadWarning)
        self.strict = True
        self.resolvedObjects = {}
        self.xrefIndex = 0
        if isinstance(stream, str):
            fileobj = open(stream, 'rb')
            stream = StringIO.StringIO(fileobj.read())
            fileobj.close()
        self.read(stream=stream)
        self.stream = stream
        self._override_encryption = False
        self._objects = []
        self.flattenedPages = None

        self.not_use_obj_num = 0
        self._retriveObjects()

        self.not_find_obj_num = len([c for c in self._objects if isinstance(c, NotFoundObject)])

        for o in self._objects:
            queue = [o]
            iii = 0
            while iii < len(queue):
                obj = queue[iii]
                iii += 1
                if isinstance(obj, IndirectObject):
                    obj.pdf = None
                keys = None
                if isinstance(obj, DictionaryObject):
                    keys = obj.keys()
                elif isinstance(obj, ArrayObject):
                    keys = xrange(len(obj))
                if keys is not None:
                    for k in keys:
                        queue.append(obj[k])



    def _addObject(self, obj):
        self._objects.append(obj)
        return IndirectObject(len(self._objects), 0, self)

    def _retriveObjects(self):
        self._root_object = copy.copy(self.trailer['/Root'].getObject())
        self._root = self._addObject(self._root_object)

        raw_root_indirect = self.trailer.raw_get('/Root')
        indirect_map = {
            (raw_root_indirect.generation, raw_root_indirect.idnum): self._root
        }
        obj_queue = [self._root_object]
        ii = 0
        while ii < len(obj_queue):
            this_obj = obj_queue[ii]
            ii += 1
            keys = None
            if isinstance(this_obj, dict):
                keys = this_obj.keys()
            elif isinstance(this_obj, list):
                keys = xrange(len(this_obj))
            if keys is not None:
                for k in keys:
                    if isinstance(this_obj[k], IndirectObject):
                        if (this_obj[k].generation, this_obj[k].idnum) not in indirect_map:
                            new_obj = self.getObject(this_obj[k])
                            new_indirect = self._addObject(new_obj)
                            indirect_map[(this_obj[k].generation, this_obj[k].idnum)] = new_indirect
                            obj_queue.append(new_obj)
                        this_obj[k] = indirect_map[(this_obj[k].generation, this_obj[k].idnum)]
                    elif isinstance(this_obj[k], dict) or isinstance(this_obj[k], list):
                        obj_queue.append(this_obj[k])
        self.not_use_obj_num = len(list(set(self.xref[0].keys())-set([c[1] for c in indirect_map.keys()])))
        pass

    def write(self, stream):
        if hasattr(stream, 'mode') and 'b' not in stream.mode:
            print 'the stream not open in binary mode!'
            raise Exception()
        need_close = False
        if isinstance(stream, str):
            stream = open(stream, 'wb')
            need_close = True

        # Begin writing:
        object_positions = []
        stream.write("%PDF-1.3" + "\n")
        stream.write("%\xE2\xE3\xCF\xD3\n")
        for i in range(len(self._objects)):
            idnum = (i + 1)
            obj = self._objects[i]
            object_positions.append(stream.tell())
            stream.write(str(idnum) + " 0 obj\n")
            obj.writeToStream(stream, None)
            stream.write("\nendobj\n")

        # xref table
        xref_location = stream.tell()
        stream.write("xref\n")
        stream.write("0 %s\n" % (len(self._objects) + 1))
        stream.write("%010d %05d f \n" % (0, 65535))
        for offset in object_positions:
            stream.write("%010d %05d n \n" % (offset, 0))

        # trailer
        stream.write("trailer\n")
        trailer = DictionaryObject()
        trailer.update({
            NameObject("/Size"): NumberObject(len(self._objects) + 1),
            NameObject("/Root"): self._root,
        })
        if hasattr(self, "_ID"):
            trailer[NameObject("/ID")] = self._ID
        if hasattr(self, "_encrypt"):
            trailer[NameObject("/Encrypt")] = self._encrypt
        trailer.writeToStream(stream, None)

        # eof
        stream.write("\nstartxref\n%s\n%%%%EOF\n" % (xref_location))
        if need_close:
            stream.close()

    def getNumPages(self):
        """
        Calculates the number of pages in this PDF file.

        :return: number of pages
        :rtype: int
        :raises PdfReadError: if file is encrypted and restrictions prevent
            this action.
        """

        # Flattened pages will not work on an Encrypted PDF;
        # the PDF file's page count is used in this case. Otherwise,
        # the original method (flattened page count) is used.
        if self.isEncrypted:
            try:
                self._override_encryption = True
                self.decrypt('')
                return self.trailer["/Root"]["/Pages"]["/Count"]
            except:
                raise utils.PdfReadError("File has not been decrypted")
            finally:
                self._override_encryption = False
        else:
            if self.flattenedPages == None:
                self._flatten()
            return len(self.flattenedPages)

    numPages = property(lambda self: self.getNumPages(), None, None)

    def _flatten(self, pages=None, inherit=None, indirectRef=None):
        inheritablePageAttributes = (
            NameObject("/Resources"), NameObject("/MediaBox"),
            NameObject("/CropBox"), NameObject("/Rotate")
            )
        if inherit == None:
            inherit = dict()
        if pages == None:
            self.flattenedPages = []
            catalog = self.trailer["/Root"].getObject()
            pages = catalog["/Pages"].getObject()

        t = "/Pages"
        if "/Type" in pages:
            t = pages["/Type"]

        if t == "/Pages":
            for attr in inheritablePageAttributes:
                if attr in pages:
                    inherit[attr] = pages[attr]
            for page in pages["/Kids"]:
                addt = {}
                if isinstance(page, IndirectObject):
                    addt["indirectRef"] = page
                self._flatten(page.getObject(), inherit, **addt)
        elif t == "/Page":
            for attr, value in list(inherit.items()):
                # if the page has it's own value, it does not inherit the
                # parent's value:
                if attr not in pages:
                    pages[attr] = value
            pageObj = PageObject(self, indirectRef)
            pageObj.update(pages)
            self.flattenedPages.append(pageObj)

    def readObjectHeader(self, stream):
        # Should never be necessary to read out whitespace, since the
        # cross-reference table should put us in the right spot to read the
        # object header.  In reality... some files have stupid cross reference
        # tables that are off by whitespace bytes.
        extra = False
        utils.skipOverComment(stream)
        extra |= utils.skipOverWhitespace(stream); stream.seek(-1, 1)
        idnum = readUntilWhitespace(stream)
        extra |= utils.skipOverWhitespace(stream); stream.seek(-1, 1)
        generation = readUntilWhitespace(stream)
        obj = stream.read(3)
        readNonWhitespace(stream)
        stream.seek(-1, 1)
        if (extra and self.strict):
            #not a fatal error
            warnings.warn("Superfluous whitespace found in object header %s %s" % \
                          (idnum, generation), utils.PdfReadWarning)
        return int(idnum), int(generation)

    def cacheGetIndirectObject(self, generation, idnum):
        debug = False
        out = self.resolvedObjects.get((generation, idnum))
        if debug and out: print(("cache hit: %d %d"%(idnum, generation)))
        elif debug: print(("cache miss: %d %d"%(idnum, generation)))
        return out

    def cacheIndirectObject(self, generation, idnum, obj):
        # return None # Sometimes we want to turn off cache for debugging.
        if (generation, idnum) in self.resolvedObjects:
            msg = "Overwriting cache for %s %s"%(generation, idnum)
            if self.strict: raise utils.PdfReadError(msg)
            else:
                warnings.warn(msg)
        self.resolvedObjects[(generation, idnum)] = obj
        return obj

    def getIsEncrypted(self):
        return "/Encrypt" in self.trailer

    isEncrypted = property(lambda self: self.getIsEncrypted(), None, None)

    def _getObjectFromStream(self, indirectReference):
        # indirect reference to object in object stream
        # read the entire object stream into memory
        stmnum, idx = self.xref_objStm[indirectReference.idnum]
        objStm = IndirectObject(stmnum, 0, self).getObject()
        # This is an xref to a stream, so its type better be a stream
        assert objStm['/Type'] == '/ObjStm'
        # /N is the number of indirect objects in the stream
        assert idx < objStm['/N']
        streamData = StringIO.StringIO(objStm.getData())
        for i in range(objStm['/N']):
            readNonWhitespace(streamData)
            streamData.seek(-1, 1)
            objnum = NumberObject.readFromStream(streamData)
            readNonWhitespace(streamData)
            streamData.seek(-1, 1)
            offset = NumberObject.readFromStream(streamData)
            readNonWhitespace(streamData)
            streamData.seek(-1, 1)
            if objnum != indirectReference.idnum:
                # We're only interested in one object
                continue
            if self.strict and idx != i:
                raise utils.PdfReadError("Object is in wrong index.")
            streamData.seek(objStm['/First']+offset, 0)
            try:
                obj = readObject(streamData, self)
            except utils.PdfStreamError as e:
                # Stream object cannot be read. Normally, a critical error, but
                # Adobe Reader doesn't complain, so continue (in strict mode?)
                e = sys.exc_info()[1]
                warnings.warn("Invalid stream (index %d) within object %d %d: %s" % \
                      (i, indirectReference.idnum, indirectReference.generation, e), utils.PdfReadWarning)

                if self.strict:
                    raise utils.PdfReadError("Can't read object stream: %s"%e)
                # Replace with null. Hopefully it's nothing important.
                obj = NullObject()
            return obj

        if self.strict: raise utils.PdfReadError("This is a fatal error in strict mode.")
        return NullObject()

    def _authenticateUserPassword(self, password):
        encrypt = self.trailer['/Encrypt'].getObject()
        rev = encrypt['/R'].getObject()
        owner_entry = encrypt['/O'].getObject()
        p_entry = encrypt['/P'].getObject()
        id_entry = self.trailer['/ID'].getObject()
        id1_entry = id_entry[0].getObject()
        real_U = encrypt['/U'].getObject().original_bytes
        if rev == 2:
            U, key = _alg34(password, owner_entry, p_entry, id1_entry)
        elif rev >= 3:
            U, key = _alg35(password, rev,
                    encrypt["/Length"].getObject() // 8, owner_entry,
                    p_entry, id1_entry,
                    encrypt.get("/EncryptMetadata", BooleanObject(False)).getObject())
            U, real_U = U[:16], real_U[:16]
        return U == real_U, key

    def _decryptObject(self, obj, key):
        if isinstance(obj, ByteStringObject) or isinstance(obj, TextStringObject):
            obj = createStringObject(utils.RC4_encrypt(key, obj.original_bytes))
        elif isinstance(obj, StreamObject):
            obj._data = utils.RC4_encrypt(key, obj._data)
        elif isinstance(obj, DictionaryObject):
            for dictkey, value in list(obj.items()):
                obj[dictkey] = self._decryptObject(value, key)
        elif isinstance(obj, ArrayObject):
            for i in range(len(obj)):
                obj[i] = self._decryptObject(obj[i], key)
        return obj

    def decrypt(self, password):
        """
        When using an encrypted / secured PDF file with the PDF Standard
        encryption handler, this function will allow the file to be decrypted.
        It checks the given password against the document's user password and
        owner password, and then stores the resulting decryption key if either
        password is correct.

        It does not matter which password was matched.  Both passwords provide
        the correct decryption key that will allow the document to be used with
        this library.

        :param str password: The password to match.
        :return: ``0`` if the password failed, ``1`` if the password matched the user
            password, and ``2`` if the password matched the owner password.
        :rtype: int
        :raises NotImplementedError: if document uses an unsupported encryption
            method.
        """

        self._override_encryption = True
        try:
            return self._decrypt(password)
        finally:
            self._override_encryption = False

    def _decrypt(self, password):
        encrypt = self.trailer['/Encrypt'].getObject()
        if encrypt['/Filter'] != '/Standard':
            raise NotImplementedError("only Standard PDF encryption handler is available")
        if not (encrypt['/V'] in (1, 2)):
            raise NotImplementedError("only algorithm code 1 and 2 are supported. This PDF uses code %s" % encrypt['/V'])
        user_password, key = self._authenticateUserPassword(password)
        if user_password:
            self._decryption_key = key
            return 1
        else:
            rev = encrypt['/R'].getObject()
            if rev == 2:
                keylen = 5
            else:
                keylen = encrypt['/Length'].getObject() // 8
            key = _alg33_1(password, rev, keylen)
            real_O = encrypt["/O"].getObject()
            if rev == 2:
                userpass = utils.RC4_encrypt(key, real_O)
            else:
                val = real_O
                for i in range(19, -1, -1):
                    new_key = ''
                    for l in range(len(key)):
                        new_key += chr(ord(key[l]) ^ i)
                    val = utils.RC4_encrypt(new_key, val)
                userpass = val
            owner_password, key = self._authenticateUserPassword(userpass)
            if owner_password:
                self._decryption_key = key
                return 2
        return 0

    def getObject(self, indirectReference):
        debug = False
        if debug: print(("looking at:", indirectReference.idnum, indirectReference.generation))
        retval = self.cacheGetIndirectObject(indirectReference.generation,
                                                indirectReference.idnum)
        if retval != None:
            return retval
        if indirectReference.generation == 0 and \
                        indirectReference.idnum in self.xref_objStm:
            retval = self._getObjectFromStream(indirectReference)
        elif indirectReference.generation in self.xref and \
                indirectReference.idnum in self.xref[indirectReference.generation]:
            start = self.xref[indirectReference.generation][indirectReference.idnum]
            if debug: print(("  Uncompressed Object", indirectReference.idnum, indirectReference.generation, ":", start))
            self.stream.seek(start, 0)
            idnum, generation = self.readObjectHeader(self.stream)
            if idnum != indirectReference.idnum and self.xrefIndex:
                # Xref table probably had bad indexes due to not being zero-indexed
                if self.strict:
                    raise utils.PdfReadError("Expected object ID (%d %d) does not match actual (%d %d); xref table not zero-indexed." \
                                     % (indirectReference.idnum, indirectReference.generation, idnum, generation))
                else: pass # xref table is corrected in non-strict mode
            elif idnum != indirectReference.idnum and self.strict:
                # some other problem
                raise utils.PdfReadError("Expected object ID (%d %d) does not match actual (%d %d)." \
                                         % (indirectReference.idnum, indirectReference.generation, idnum, generation))
            if self.strict:
                assert generation == indirectReference.generation
            retval = readObject(self.stream, self)

            # override encryption is used for the /Encrypt dictionary
            if not self._override_encryption and self.isEncrypted:
                # if we don't have the encryption key:
                if not hasattr(self, '_decryption_key'):
                    # raise utils.PdfReadError("file has not been decrypted")
                    raise utils.PdfCannotDecrypted('file cannot be decrypted')
                # otherwise, decrypt here...
                import struct
                pack1 = struct.pack("<i", indirectReference.idnum)[:3]
                pack2 = struct.pack("<i", indirectReference.generation)[:2]
                key = self._decryption_key + pack1 + pack2
                assert len(key) == (len(self._decryption_key) + 5)
                md5_hash = md5(key).digest()
                key = md5_hash[:min(16, len(self._decryption_key) + 5)]
                retval = self._decryptObject(retval, key)
        else:
            warnings.warn("Object %d %d not defined."%(indirectReference.idnum,
                        indirectReference.generation), utils.PdfReadWarning)
            #if self.strict:
            # raise utils.PdfReadError("Could not find object.")
            retval = NotFoundObject()
        self.cacheIndirectObject(indirectReference.generation,
                    indirectReference.idnum, retval)
        return retval

    def read(self, stream):
        # start at the end:
        stream.seek(-1, 2)
        if not stream.tell():
            raise utils.PdfReadError('Cannot read an empty file')
        last1K = stream.tell() - 1024 + 1  # offset of last 1024 bytes of stream
        line = ''
        while line[:5] != "%%EOF":
            if stream.tell() < last1K:
                raise utils.PdfReadError("EOF marker not found")
            line = self.readNextEndLine(stream)

        # find startxref entry - the location of the xref table
        line = self.readNextEndLine(stream)
        try:
            startxref = int(line)
        except ValueError:
            # 'startxref' may be on the same line as the location
            if not line.startswith("startxref"):
                raise utils.PdfReadError("startxref not found")
            startxref = int(line[9:].strip())
            warnings.warn("startxref on same line as offset")
        else:
            line = self.readNextEndLine(stream)
            if line[:9] != "startxref":
                raise utils.PdfReadError("startxref not found")

        # read all cross reference tables and their trailers
        self.xref = {}
        self.xref_objStm = {}
        self.trailer = DictionaryObject()
        while True:
            # load the xref table
            stream.seek(startxref, 0)
            x = stream.read(1)
            if x == "x":
                # standard cross-reference table
                ref = stream.read(4)
                if ref[:3] != "ref":
                    raise utils.PdfReadError("xref table read error")
                readNonWhitespace(stream)
                stream.seek(-1, 1)
                firsttime = True;  # check if the first time looking at the xref table
                while True:
                    num = readObject(stream, self)
                    if firsttime and num != 0:
                        self.xrefIndex = num
                        if self.strict:
                            warnings.warn("Xref table not zero-indexed. ID numbers for objects will be corrected.",
                                          utils.PdfReadWarning)
                            # if table not zero indexed, could be due to error from when PDF was created
                            # which will lead to mismatched indices later on, only warned and corrected if self.strict=True
                    firsttime = False
                    readNonWhitespace(stream)
                    stream.seek(-1, 1)
                    size = readObject(stream, self)
                    readNonWhitespace(stream)
                    stream.seek(-1, 1)
                    cnt = 0
                    while cnt < size:
                        line = stream.read(20)

                        # It's very clear in section 3.4.3 of the PDF spec
                        # that all cross-reference table lines are a fixed
                        # 20 bytes (as of PDF 1.7). However, some files have
                        # 21-byte entries (or more) due to the use of \r\n
                        # (CRLF) EOL's. Detect that case, and adjust the line
                        # until it does not begin with a \r (CR) or \n (LF).
                        while line[0] in "\x0D\x0A":
                            stream.seek(-20 + 1, 1)
                            line = stream.read(20)

                        # On the other hand, some malformed PDF files
                        # use a single character EOL without a preceeding
                        # space.  Detect that case, and seek the stream
                        # back one character.  (0-9 means we've bled into
                        # the next xref entry, t means we've bled into the
                        # text "trailer"):
                        if line[-1] in "0123456789t":
                            stream.seek(-1, 1)

                        offset, generation = line[:16].split(" ")
                        offset, generation = int(offset), int(generation)
                        if generation not in self.xref:
                            self.xref[generation] = {}
                        if num in self.xref[generation]:
                            # It really seems like we should allow the last
                            # xref table in the file to override previous
                            # ones. Since we read the file backwards, assume
                            # any existing key is already set correctly.
                            pass
                        else:
                            self.xref[generation][num] = offset
                        cnt += 1
                        num += 1
                    readNonWhitespace(stream)
                    stream.seek(-1, 1)
                    trailertag = stream.read(7)
                    if trailertag != "trailer":
                        # more xrefs!
                        stream.seek(-7, 1)
                    else:
                        break
                readNonWhitespace(stream)
                stream.seek(-1, 1)
                newTrailer = readObject(stream, self)
                for key, value in list(newTrailer.items()):
                    if key not in self.trailer:
                        self.trailer[key] = value
                if "/Prev" in newTrailer:
                    startxref = newTrailer["/Prev"]
                else:
                    break
            elif x.isdigit():
                # PDF 1.5+ Cross-Reference Stream
                stream.seek(-1, 1)
                idnum, generation = self.readObjectHeader(stream)
                xrefstream = readObject(stream, self)
                assert xrefstream["/Type"] == "/XRef"
                self.cacheIndirectObject(generation, idnum, xrefstream)
                streamData = StringIO.StringIO(xrefstream.getData())
                # Index pairs specify the subsections in the dictionary. If
                # none create one subsection that spans everything.
                idx_pairs = xrefstream.get("/Index", [0, xrefstream.get("/Size")])
                entrySizes = xrefstream.get("/W")
                assert len(entrySizes) >= 3
                if self.strict and len(entrySizes) > 3:
                    raise utils.PdfReadError("Too many entry sizes: %s" % entrySizes)

                def getEntry(i):
                    # Reads the correct number of bytes for each entry. See the
                    # discussion of the W parameter in PDF spec table 17.
                    if entrySizes[i] > 0:
                        d = streamData.read(entrySizes[i])
                        return convertToInt(d, entrySizes[i])

                    # PDF Spec Table 17: A value of zero for an element in the
                    # W array indicates...the default value shall be used
                    if i == 0:
                        return 1  # First value defaults to 1
                    else:
                        return 0

                def used_before(num, generation):
                    # We move backwards through the xrefs, don't replace any.
                    return num in self.xref.get(generation, []) or \
                           num in self.xref_objStm

                # Iterate through each subsection
                last_end = 0
                for start, size in self._pairs(idx_pairs):
                    # The subsections must increase
                    assert start >= last_end
                    last_end = start + size
                    for num in range(start, start + size):
                        # The first entry is the type
                        xref_type = getEntry(0)
                        # The rest of the elements depend on the xref_type
                        if xref_type == 0:
                            # linked list of free objects
                            next_free_object = getEntry(1)
                            next_generation = getEntry(2)
                        elif xref_type == 1:
                            # objects that are in use but are not compressed
                            byte_offset = getEntry(1)
                            generation = getEntry(2)
                            if generation not in self.xref:
                                self.xref[generation] = {}
                            if not used_before(num, generation):
                                self.xref[generation][num] = byte_offset
                        elif xref_type == 2:
                            # compressed objects
                            objstr_num = getEntry(1)
                            obstr_idx = getEntry(2)
                            generation = 0  # PDF spec table 18, generation is 0
                            if not used_before(num, generation):
                                self.xref_objStm[num] = (objstr_num, obstr_idx)
                        elif self.strict:
                            raise utils.PdfReadError("Unknown xref type: %s" %
                                                     xref_type)

                trailerKeys = "/Root", "/Encrypt", "/Info", "/ID"
                for key in trailerKeys:
                    if key in xrefstream and key not in self.trailer:
                        self.trailer[NameObject(key)] = xrefstream.raw_get(key)
                if "/Prev" in xrefstream:
                    startxref = xrefstream["/Prev"]
                else:
                    break
            else:
                # bad xref character at startxref.  Let's see if we can find
                # the xref table nearby, as we've observed this error with an
                # off-by-one before.
                stream.seek(-11, 1)
                tmp = stream.read(20)
                xref_loc = tmp.find("xref")
                if xref_loc != -1:
                    startxref -= (10 - xref_loc)
                    continue
                # No explicit xref table, try finding a cross-reference stream.
                stream.seek(startxref, 0)
                found = False
                for look in range(5):
                    if stream.read(1).isdigit():
                        # This is not a standard PDF, consider adding a warning
                        startxref += look
                        found = True
                        break
                if found:
                    continue
                # no xref table found at specified location
                raise utils.PdfReadError("Could not find xref table at specified location")
        # if not zero-indexed, verify that the table is correct; change it if necessary
        if self.xrefIndex and not self.strict:
            loc = stream.tell()
            for gen in self.xref:
                if gen == 65535: continue
                for id in self.xref[gen]:
                    stream.seek(self.xref[gen][id], 0)
                    try:
                        pid, pgen = self.readObjectHeader(stream)
                    except ValueError:
                        break
                    if pid == id - self.xrefIndex:
                        self._zeroXref(gen)
                        break
                    # if not, then either it's just plain wrong, or the non-zero-index is actually correct
            stream.seek(loc, 0)  # return to where it was

    def _pairs(self, array):
        i = 0
        while True:
            yield array[i], array[i+1]
            i += 2
            if (i+1) >= len(array):
                break

    def _zeroXref(self, generation):
        self.xref[generation] = dict( (k-self.xrefIndex, v) for (k, v) in list(self.xref[generation].items()) )

    def readNextEndLine(self, stream):
        debug = False
        if debug: print(">>readNextEndLine")
        line = ""
        while True:
            # Prevent infinite loops in malformed PDFs
            if stream.tell() == 0:
                raise utils.PdfReadError("Could not read malformed PDF file")
            x = stream.read(1)
            if debug: print(("  x:", x, "%x" % ord(x)))
            if stream.tell() < 2:
                raise utils.PdfReadError("EOL marker not found")
            stream.seek(-2, 1)
            if x == '\n' or x == '\r':  ## \n = LF; \r = CR
                crlf = False
                while x == '\n' or x == '\r':
                    if debug:
                        if ord(x) == 0x0D:
                            print("  x is CR 0D")
                        elif ord(x) == 0x0A:
                            print("  x is LF 0A")
                    x = stream.read(1)
                    if x == '\n' or x == '\r':  # account for CR+LF
                        stream.seek(-1, 1)
                        crlf = True
                    if stream.tell() < 2:
                        raise utils.PdfReadError("EOL marker not found")
                    stream.seek(-2, 1)
                stream.seek(2 if crlf else 1, 1)  # if using CR+LF, go back 2 bytes, else 1
                break
            else:
                if debug: print("  x is neither")
                line = x + line
                if debug: print(("  RNEL line:", line))
        if debug: print("leaving RNEL")
        return line


class PageObject(DictionaryObject):
    """
    This class represents a single page within a PDF file.  Typically this
    object will be created by accessing the
    :meth:`getPage()<PyPDF2.PdfFileReader.getPage>` method of the
    :class:`PdfFileReader<PyPDF2.PdfFileReader>` class, but it is
    also possible to create an empty page with the
    :meth:`createBlankPage()<PageObject.createBlankPage>` static method.

    :param pdf: PDF file the page belongs to.
    :param indirectRef: Stores the original indirect reference to
        this object in its source PDF
    """
    def __init__(self, pdf=None, indirectRef=None):
        DictionaryObject.__init__(self)
        self.pdf = pdf
        self.indirectRef = indirectRef



def convertToInt(d, size):
    if size > 8:
        raise utils.PdfReadError("invalid size in convertToInt")
    d = "\x00\x00\x00\x00\x00\x00\x00\x00" + d
    d = d[-8:]
    return struct.unpack(">q", d)[0]


# ref: pdf1.8 spec section 3.5.2 algorithm 3.2
_encryption_padding = '\x28\xbf\x4e\x5e\x4e\x75\x8a\x41\x64\x00\x4e\x56' + \
        '\xff\xfa\x01\x08\x2e\x2e\x00\xb6\xd0\x68\x3e\x80\x2f\x0c' + \
        '\xa9\xfe\x64\x53\x69\x7a'


# Implementation of algorithm 3.2 of the PDF standard security handler,
# section 3.5.2 of the PDF 1.6 reference.
def _alg32(password, rev, keylen, owner_entry, p_entry, id1_entry, metadata_encrypt=True):
    # 1. Pad or truncate the password string to exactly 32 bytes.  If the
    # password string is more than 32 bytes long, use only its first 32 bytes;
    # if it is less than 32 bytes long, pad it by appending the required number
    # of additional bytes from the beginning of the padding string
    # (_encryption_padding).
    password = (password + _encryption_padding)[:32]
    # 2. Initialize the MD5 hash function and pass the result of step 1 as
    # input to this function.
    import struct
    m = md5(password)
    # 3. Pass the value of the encryption dictionary's /O entry to the MD5 hash
    # function.
    m.update(owner_entry.original_bytes)
    # 4. Treat the value of the /P entry as an unsigned 4-byte integer and pass
    # these bytes to the MD5 hash function, low-order byte first.
    p_entry = struct.pack('<i', p_entry)
    m.update(p_entry)
    # 5. Pass the first element of the file's file identifier array to the MD5
    # hash function.
    m.update(id1_entry.original_bytes)
    # 6. (Revision 3 or greater) If document metadata is not being encrypted,
    # pass 4 bytes with the value 0xFFFFFFFF to the MD5 hash function.
    if rev >= 3 and not metadata_encrypt:
        m.update("\xff\xff\xff\xff")
    # 7. Finish the hash.
    md5_hash = m.digest()
    # 8. (Revision 3 or greater) Do the following 50 times: Take the output
    # from the previous MD5 hash and pass the first n bytes of the output as
    # input into a new MD5 hash, where n is the number of bytes of the
    # encryption key as defined by the value of the encryption dictionary's
    # /Length entry.
    if rev >= 3:
        for i in range(50):
            md5_hash = md5(md5_hash[:keylen]).digest()
    # 9. Set the encryption key to the first n bytes of the output from the
    # final MD5 hash, where n is always 5 for revision 2 but, for revision 3 or
    # greater, depends on the value of the encryption dictionary's /Length
    # entry.
    return md5_hash[:keylen]


# Implementation of algorithm 3.3 of the PDF standard security handler,
# section 3.5.2 of the PDF 1.6 reference.
def _alg33(owner_pwd, user_pwd, rev, keylen):
    # steps 1 - 4
    key = _alg33_1(owner_pwd, rev, keylen)
    # 5. Pad or truncate the user password string as described in step 1 of
    # algorithm 3.2.
    user_pwd = (user_pwd + _encryption_padding)[:32]
    # 6. Encrypt the result of step 5, using an RC4 encryption function with
    # the encryption key obtained in step 4.
    val = utils.RC4_encrypt(key, user_pwd)
    # 7. (Revision 3 or greater) Do the following 19 times: Take the output
    # from the previous invocation of the RC4 function and pass it as input to
    # a new invocation of the function; use an encryption key generated by
    # taking each byte of the encryption key obtained in step 4 and performing
    # an XOR operation between that byte and the single-byte value of the
    # iteration counter (from 1 to 19).
    if rev >= 3:
        for i in range(1, 20):
            new_key = ''
            for l in range(len(key)):
                new_key += chr(ord(key[l]) ^ i)
            val = utils.RC4_encrypt(new_key, val)
    # 8. Store the output from the final invocation of the RC4 as the value of
    # the /O entry in the encryption dictionary.
    return val


# Steps 1-4 of algorithm 3.3
def _alg33_1(password, rev, keylen):
    # 1. Pad or truncate the owner password string as described in step 1 of
    # algorithm 3.2.  If there is no owner password, use the user password
    # instead.
    password = (password + _encryption_padding)[:32]
    # 2. Initialize the MD5 hash function and pass the result of step 1 as
    # input to this function.
    m = md5(password)
    # 3. (Revision 3 or greater) Do the following 50 times: Take the output
    # from the previous MD5 hash and pass it as input into a new MD5 hash.
    md5_hash = m.digest()
    if rev >= 3:
        for i in range(50):
            md5_hash = md5(md5_hash).digest()
    # 4. Create an RC4 encryption key using the first n bytes of the output
    # from the final MD5 hash, where n is always 5 for revision 2 but, for
    # revision 3 or greater, depends on the value of the encryption
    # dictionary's /Length entry.
    key = md5_hash[:keylen]
    return key



# Implementation of algorithm 3.4 of the PDF standard security handler,
# section 3.5.2 of the PDF 1.6 reference.
def _alg34(password, owner_entry, p_entry, id1_entry):
    # 1. Create an encryption key based on the user password string, as
    # described in algorithm 3.2.
    key = _alg32(password, 2, 5, owner_entry, p_entry, id1_entry)
    # 2. Encrypt the 32-byte padding string shown in step 1 of algorithm 3.2,
    # using an RC4 encryption function with the encryption key from the
    # preceding step.
    U = utils.RC4_encrypt(key, _encryption_padding)
    # 3. Store the result of step 2 as the value of the /U entry in the
    # encryption dictionary.
    return U, key


# Implementation of algorithm 3.4 of the PDF standard security handler,
# section 3.5.2 of the PDF 1.6 reference.
def _alg35(password, rev, keylen, owner_entry, p_entry, id1_entry, metadata_encrypt):
    # 1. Create an encryption key based on the user password string, as
    # described in Algorithm 3.2.
    key = _alg32(password, rev, keylen, owner_entry, p_entry, id1_entry)
    # 2. Initialize the MD5 hash function and pass the 32-byte padding string
    # shown in step 1 of Algorithm 3.2 as input to this function.
    m = md5()
    m.update(_encryption_padding)
    # 3. Pass the first element of the file's file identifier array (the value
    # of the ID entry in the document's trailer dictionary; see Table 3.13 on
    # page 73) to the hash function and finish the hash.  (See implementation
    # note 25 in Appendix H.)
    m.update(id1_entry.original_bytes)
    md5_hash = m.digest()
    # 4. Encrypt the 16-byte result of the hash, using an RC4 encryption
    # function with the encryption key from step 1.
    val = utils.RC4_encrypt(key, md5_hash)
    # 5. Do the following 19 times: Take the output from the previous
    # invocation of the RC4 function and pass it as input to a new invocation
    # of the function; use an encryption key generated by taking each byte of
    # the original encryption key (obtained in step 2) and performing an XOR
    # operation between that byte and the single-byte value of the iteration
    # counter (from 1 to 19).
    for i in range(1, 20):
        new_key = ''
        for l in range(len(key)):
            new_key += chr(ord(key[l]) ^ i)
        val = utils.RC4_encrypt(new_key, val)
    # 6. Append 16 bytes of arbitrary padding to the output from the final
    # invocation of the RC4 function and store the 32-byte result as the value
    # of the U entry in the encryption dictionary.
    # (implementator note: I don't know what "arbitrary padding" is supposed to
    # mean, so I have used null bytes.  This seems to match a few other
    # people's implementations)
    return val + ('\x00' * 16), key
