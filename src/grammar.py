#   Domato - grammar parser and generator
#   --------------------------------------
#
#   Written and maintained by Ivan Fratric <ifratric@google.com>
#
#   Copyright 2017 Google Inc. All Rights Reserved.
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


from __future__ import print_function

import bisect
import cgi
import os
import random
import re
import struct
import copy

_INT_RANGES = {
    'int': [-2147483648, 2147483647],
    'int32': [-2147483648, 2147483647],
    'uint32': [0, 4294967295],
    'int8': [-128, 127],
    'uint8': [0, 255],
    'int16': [-32768, 32767],
    'uint16': [0, 65536],
    'int64': [-9223372036854775808, 9223372036854775807],
    'uint64': [0, 18446744073709551615]
}



_INT_FORMATS = {
    'int': 'i',
    'int32': 'i',
    'uint32': 'I',
    'int8': 'b',
    'uint8': 'B',
    'int16': 'h',
    'uint16': 'H',
    'int64': 'q',
    'uint64': 'Q'
}

_NONINTERESTING_TYPES = {
    'short',
    'long',
    'DOMString',
    'JString',
    'boolean',
    'float',
    'double',
    'TempVar',
    'int',
}


class Error(Exception):
    pass


class GrammarError(Error):
    """An exception class for parsing errors."""
    pass


class RecursionError(Error):
    """An exception class for reaching maximum recursion depth."""
    pass


class Grammar(object):
    """Parses grammar and generates corresponding languages.

    To use you need to first parse the grammar definition file, example:
    >>> grammar = Grammar()
    >>> grammar.parse_from_file('grammar.txt')
    After this, you can generate the language starting from the root symbol:
    >>> ret = grammar.generate_root()
    Or a specific symbol
    >>> ret = grammar.generate_symbol('foo')
    """

    def __init__(self):
        self._root = ''
        self._creators = {}
        self._nonrecursive_creators = {}
        self._all_rules = []
        self._interesting_lines = {}
        self._all_nonhelper_lines = [] # all nonhelper indices of self._creators
        self._all_prerun_lines = []

        self._creator_cdfs = {}
        self._nonrecursivecreator_cdfs = {}

        self._var_format = 'var%05d'

        self._definitions_dir = '.'

        self._imports = {}

        self._functions = {}
        self._blocks = {}

        self._line_guard = ''

        self._recursion_max = 50
        self._var_reuse_prob = 0.75
        self._interesting_line_prob = 0.8
        self._max_vars_of_same_type = 5

        self._arr_change_length_prob = 0.9
        self._attr_optional_prob = 0.7

        self._inheritance = {}

        self._cssgrammar = None

        # Helper dictionaries for creating built-in types.
        self._constant_types = {
            'lt': '<',
            'gt': '>',
            'hash': '#',
            'cr': chr(13),
            'lf': chr(10),
            'space': ' ',
            'tab': chr(9),
            'ex': '!'
        }

        self._built_in_types = {
            'int': self._generate_int,
            'int32': self._generate_int,
            'uint32': self._generate_int,
            'int8': self._generate_int,
            'uint8': self._generate_int,
            'int16': self._generate_int,
            'uint16': self._generate_int,
            'int64': self._generate_int,
            'uint64': self._generate_int,
            'float': self._generate_float,
            'double': self._generate_float,
            'char': self._generate_char,
            'string': self._generate_string,
            'htmlsafestring': self._generate_html_string,
            'hex': self._generate_hex,
            'import': self._generate_import,
            'lines': self._generate_lines,
            # myself added
            'int_attr_add': self._generate_int_attr_add,
            'int_attr_mul': self._generate_int_attr_mul,
            'int_small': self._generate_int_small,
            'int_least': self._generate_int_least,
            'xll':self._generate_xll,
            'yll':self._generate_yll,
            'xur':self._generate_xur,
            'yur':self._generate_yur,
        }

        self._command_handlers = {
            'varformat': self._set_variable_format,
            'include': self._include_from_file,
            'import': self._import_grammar,
            'lineguard': self._set_line_guard,
            'max_recursion': self._set_recursion_depth,
            'var_reuse_prob': self._set_var_reuse_probability,
            'extends': self._set_extends
        }

        self._block_action_handlers = {
            'fuzzall':self._block_fuzzall,
            'expand':self._block_expand
        }


    def _generate_int_attr_add(self, part):
        r = random.randint(0, 99)
        if r<60:
            return str(random.choice([-1, 0, 1]))
        elif r<80:
            return str(random.randint(-16, 16))
        else:
            return str(random.randint(-256, 256))

    def _generate_int_attr_mul(self, part):
        r = random.randint(0, 99)
        if r < 60:
            return str(random.choice([-1, 0, 1]))
        elif r < 80:
            return str(random.randint(-16, 16))
        else:
            return str(random.randint(-256, 256))

    def _generate_xll(self, part):
        if random.randint(0, 99) < 50:
            return str(random.randint(0,450))
        else:
            return str(random.randint(0,50))

    def _generate_yll(self, part):
        if random.randint(0, 99) < 50:
            return str(random.randint(0,450))
        else:
            return str(random.randint(0,50))

    def _generate_xur(self, part):
        if random.randint(0, 99) < 50:
            return str(random.randint(400,1000))
        else:
            return str(random.randint(50, 100))

    def _generate_yur(self, part):
        if random.randint(0, 99) < 50:
            return str(random.randint(400,1000))
        else:
            return str(random.randint(50, 100))

    def _generate_int_small(self, part):
        return str(random.randint(0, 1024))

    def _generate_int_least(self, part):
        return str(random.randint(0, 16))

    def _block_fuzzall(self, args, context):
        var_type, var_name = args.split()
        interestings_lines = copy.deepcopy(self._interesting_lines[var_type])
        random.shuffle(interestings_lines)
        lines_top = len(context['lines'])
        for i in range(len(interestings_lines)):
            idx = interestings_lines[i]
            creator = copy.deepcopy(self._creators['line'][idx])
            for part in creator['parts']:
                if part['type'] == 'tag' and part['tagname'] == var_type and 'new' not in part:
                    part['type'] = 'text'
                    part['text'] = var_name
            self._expand_rule('line', creator, context, 0, False)
        if self._line_guard is not None:
            for i in range(len(context['lines'][lines_top:])):
                context['lines'][i + lines_top] = self._line_guard.replace('<line>', context['lines'][lines_top:][i])

    def _block_expand(self, args, context):
        args_parts = args.split(' ', 1)
        if len(args_parts) == 1:
            block_name = args_parts[0]
            block_args = ''
        else:
            block_name, block_args = args_parts
        self._generate_block(block_name, block_args, context)

    def _generate_block(self, name, args, context=None):
        if name not in self._blocks:
            print('Warning: no block for {}.'.format(name))
            return
        if context is None:
            context = {
                'lastvar': 0,
                'lines': [],
                'variables': {},
                'interesting_lines': [],
                'force_var_reuse': False
            }
        argnames, body = self._blocks[name]
        block_args = {n: v for n, v in zip(argnames, args.split())}
        def update_rule(rule):
            new_rule = copy.deepcopy(rule)
            for part in new_rule['parts']:
                if part['type'] == 'tag' and part['tagname'] in block_args:
                    part['type'] = 'text'
                    part['text'] = block_args[part['tagname']]
            return new_rule
        variable_ids = {}
        for rule in body:
            if rule['type'] == 'code':
                rule = update_rule(rule)
                lines_top = len(context['lines'])
                self._expand_rule('line', rule, context, 0, False, variable_ids)
                if ('noguard'not in rule or not rule['noguard']) and self._line_guard is not None:
                    for i in range(len(context['lines'][lines_top:])):
                        context['lines'][i+lines_top] = self._line_guard.replace('<line>', context['lines'][lines_top:][i])
            elif rule['type'] == 'action':
                args_rule = rule['parts']
                args_rule = update_rule(args_rule)
                tmp_context = context.copy()
                tmp_context['lines'] = []
                args = self._expand_rule('line', args_rule, tmp_context, 0, False, variable_ids)
                context['lastvar']=tmp_context['lastvar']
                self._block_action_handlers[rule['action']](args, context)
        return '\n'.join(context['lines'])

    def _string_to_int(self, s):
        return int(s, 0)

    def _generate_int(self, tag):
        """Generates integer types."""
        tag_name = tag['tagname']
        default_range = _INT_RANGES[tag_name]

        min_value = default_range[0]
        if 'min' in tag:
            min_value = self._string_to_int(tag['min'])

        max_value = default_range[1]
        if 'max' in tag:
            max_value = self._string_to_int(tag['max'])

        if min_value > max_value:
            raise GrammarError('Range error in integer tag')

        if 'for' in tag:
            for_what = tag['for']
            if for_what == "int_attr_add":
                i = random.choice([1, -1, 2, -2, 4, -4, 8, -8, 16, -16])
            elif for_what == "int_attr_mul":
                i = random.choice([0, -1, 2, -2, 4, -4, 8, -8, 16, -16])
            elif for_what == 'index':
                i = random.choice([0]*40+[1]*15+[2]*10+[3]*5+range(4,8)+random.sample(range(4, 30), 10))
        else:
            if 'min' in tag and 'max' in tag:
                i = random.randint(min_value, max_value)
            elif random.random() < 0.4:
                i = random.choice([0, 0, 1, -1, 4, -4, 8, -8, 16, -16, 0xffffffff, -0xffffffff, 0xfffffffe, -0xfffffffe])
            elif random.random() < 0.6:
                i = random.randint(-0x120, 0x1000)
            else:
                i = random.randint(min_value, max_value)

        if 'b' in tag or 'be' in tag:
            if 'be' in tag:
                fmt = '>' + _INT_FORMATS[tag_name]
            else:
                fmt = '<' + _INT_FORMATS[tag_name]
            return struct.pack(fmt, i)
        else:
            return str(i)

    def _generate_float(self, tag):
        """Generates floating point types."""
        min_value = float(tag.get('min', '0'))
        max_value = float(tag.get('max', '1'))
        if min_value > max_value:
            raise GrammarError('Range error in a float tag')
        f = min_value + random.random() * (max_value - min_value)
        if 'b' in tag:
            if tag['tagname'] == 'float':
                return struct.pack('f', f)
            else:
                return struct.pack('d', f)
        else:
            return str(f)

    def _generate_char(self, tag):
        """Generates a single character."""
        if 'code' in tag:
            return chr(self._string_to_int(tag['code']))

        min_value = self._string_to_int(tag.get('min', '0'))
        max_value = self._string_to_int(tag.get('max', '255'))
        if min_value > max_value:
            raise GrammarError('Range error in char tag')
        return chr(random.randint(min_value, max_value))

    def _generate_string(self, tag):
        """Generates a random string."""
        min_value = self._string_to_int(tag.get('min', '0'))
        max_value = self._string_to_int(tag.get('max', '255'))
        if min_value > max_value:
            raise GrammarError('Range error in string tag')
        minlen = self._string_to_int(tag.get('minlength', '0'))
        maxlen = self._string_to_int(tag.get('maxlength', '20'))
        length = random.randint(minlen, maxlen)
        charset = range(max(min_value, 33), min(max_value + 1, 127))
        ret_list = [chr(charset[int(random.random() * len(charset))])
                    for _ in range(length)]
        s = ''.join(ret_list)
        s = s.replace('\\','\\\\').replace('"','\\"')
        return '"{}"'.format(s)

    def _generate_html_string(self, tag):
        return cgi.escape(self._generate_string(tag), quote=True)

    def _generate_hex(self, tag):
        """Generates a single hex digit."""
        digit = random.randint(0, 15)
        if 'up' in tag:
            return '%X' % digit
        else:
            return '%x' % digit

    def _generate_import(self, tag):
        """Expands a symbol from another (imported) grammar."""
        if 'from' not in tag:
            raise GrammarError('import tag without from attribute')

        grammarname = tag['from']
        if grammarname not in self._imports:
            raise GrammarError('unknown import ' + grammarname)

        grammar = self._imports[grammarname]
        if 'symbol' in tag:
            symbol = tag['symbol']
            return grammar.generate_symbol(symbol)
        else:
            return grammar.generate_root()

    def _generate_lines(self, tag):
        """Generates a given number of lines of code."""
        if 'count' not in tag:
            raise GrammarError('lines tag without count attribute')

        num_lines = self._string_to_int(tag['count'])
        return '\n'.join(self._generate_code(num_lines, prerun=True))

    def generate_scripts(self, apiname, line_num):

        script_lines = ''
        if 'block_{}'.format(apiname) in self._blocks:
            block_code = self._generate_block('block_{}'.format(apiname), '')
            script_lines += block_code
        script_lines += '\n//// ****************************cut up*****************************\n\n'
        block_linecnt = len(script_lines.splitlines())
        if line_num > block_linecnt:
            script_lines += '\n'.join(self._generate_code(line_num-block_linecnt, apiname))
        return script_lines


    @staticmethod
    def _create_sub_routine(lines, subname, endmsg=None):
        if endmsg is None:
            sub = '\r\nsub {}\r\n{}\r\n{}\r\nend sub\r\n'.format(
                subname, 'On Error Resume Next','\r\n'.join(lines))
        else:
            sub = '\r\nsub {}\r\n{}\r\n{}\r\n{}\r\nend sub\r\n'.format(
                subname, 'On Error Resume Next', '\r\n'.join(lines), 'MsgBox "{}"'.format(endmsg))
        return sub

    def generate_vba_scripts(self, apiname, line_num):
        context = {
            'lastvar': 0,
            'lines': [],
            'variables': {},
            'interesting_lines': [],
            'force_var_reuse': False
        }
        sub_list = []
        subid = 0
        if line_num > 0:
            wholelines = self._generate_code(line_num, apiname, script_type='vba')
            i, step = 0, 400
            while i<len(wholelines):
                lines = wholelines[i:i+step]
                i += step
                subname = 'sub_{}'.format(str(subid))
                subbody = Grammar._create_sub_routine(lines, subname)
                subid += 1
                sub_list.append((subname, subbody))
        mainbody = Grammar._create_sub_routine([c[0] for c in sub_list], 'Document_Open', endmsg='info:end')
        sub_list.append(('Document_Open', mainbody))
        varidx = 0
        dimvar = ''
        while varidx<context['lastvar']:
            dimvar += 'dim {}\r\n'.format(','.join([self._var_format%c for c in range(varidx, varidx+50)]))
            varidx += 50
        return dimvar+''.join([c[1] for c in sub_list])

    def _generate_code(self, num_lines, apiname, foref_variables={}, initial_variables=[], last_var=0, script_type=None):
        """Generates a given number of lines of code."""


        context = {
            'lastvar': last_var,
            'lines': [],
            'variables': foref_variables,
            'interesting_lines': [],
            'force_var_reuse': False
        }

        for v in initial_variables:
            self._add_variable(v['name'], v['type'], context)

        api_related_lines = []
        for i in range(len(self._creators['line'])):
            if i not in self._all_nonhelper_lines:
                continue
            rule = self._creators['line'][i]
            for part in rule['parts']:
                if part['type'] == 'text':
                    continue
                tagname = part['tagname']
                if tagname == apiname:
                    api_related_lines.append(i)

        num_lines += len(context['lines'])
        while len(context['lines']) < num_lines :
            tmp_context = context.copy()
            try:
                if len(api_related_lines) > 0 and random.randint(0, 99) < 60:
                    lineno = random.choice(api_related_lines)
                elif (random.random() < self._interesting_line_prob) and (len(tmp_context['interesting_lines']) > 0):
                    tmp_context['force_var_reuse'] = True
                    lineno = random.choice(tmp_context['interesting_lines'])
                else:
                    lineno = random.choice(self._all_nonhelper_lines)
                creator = self._creators['line'][lineno] # creator is a rule
                self._expand_rule('line', creator, tmp_context, 0, False, script_type=script_type)
                context = tmp_context
            except RecursionError as e:
                print('Warning: ' + str(e))
        # for i in range(len(context['lines']) // 100):
        #     context['lines'].insert(
        #         random.randint(0, len(context['lines'])),
        #         'freememory();'
        #     )
        if not self._line_guard:
            guarded_lines = context['lines']
        else:
            guarded_lines = []
            for line in context['lines']:
                guarded_lines.append(self._line_guard.replace('<line>', line))
        return guarded_lines
        # return '\n'.join(guarded_lines)

    def _exec_function(self, function_name, attributes, context, ret_val):
        """Executes user-defined python code."""
        if function_name not in self._functions:
            raise GrammarError('Unknown function ' + function_name)
        compiled_function = self._functions[function_name]
        args = {
            'attributes': attributes,
            'context': context,
            'ret_val': ret_val
        }
        # pylint: disable=exec-used
        try:
            exec(compiled_function, args)
        except Exception as e:
            raise GrammarError('Error in user-defined function: %s' % str(e))
        return args['ret_val']

    def _select_creator(self, symbol, recursion_depth, force_nonrecursive):
        """Selects the creator for the given symbol.

        The creator is based on probabilities specified in the grammar or
        based on uniform distribution if no probabilities are specified.

        Args:
            symbol: The name of the symbol to get the creator rules for.
            recursion_depth: Current recursion depth
            force_nonrecursive: if True, only creators which are marked as
                'nonrecursive' will be used (if available)

        Returns:
            A dictionary describing a rule that can create a given symbol.

        Raises:
            RecursionError: If maximum recursion level was reached.
            GrammarError: If there are no rules that create a given type.
        """

        # Do we even know how to create this type?
        if symbol not in self._creators:
            raise GrammarError('No creators for type ' + symbol)

        if recursion_depth >= self._recursion_max:
            raise RecursionError(
                'Maximum recursion level reached while creating '
                'object of type' + symbol
            )
        elif force_nonrecursive and symbol in self._nonrecursive_creators:
            creators = self._nonrecursive_creators[symbol]
            cdf = self._nonrecursivecreator_cdfs[symbol]
        else:
            creators = self._creators[symbol]
            cdf = self._creator_cdfs[symbol]

        if not cdf:
            # Uniform distribution, faster
            return creators[random.randint(0, len(creators) - 1)]

        # Select a creator according to the cdf
        idx = bisect.bisect_left(cdf, random.random(), 0, len(cdf))
        return creators[idx]

    def _generate_array(self, tag, context, recursion_depth=0, force_nonrecursive=False):
        type = tag['elemtype']
        change_length = random.random() > self._arr_change_length_prob
        if 'len' in tag :
            length = self._string_to_int(tag['len'])
            if change_length:
                length = random.randint(0, 2*length)
        elif "minlen" in tag and 'maxlen' in tag:
            minlen = self._string_to_int(tag['minlen'])
            maxlen = self._string_to_int(tag['maxlen'])
            if not change_length:
                length = random.randint(minlen, maxlen)
            else:
                length = random.randint(minlen/2, 2*maxlen)
        else:
                if not change_length:
                    length = random.randint(0, 10)
                else:
                    length = random.randint(0, 20)

        if type in self._built_in_types:
            vars = [self._built_in_types[type]({'tagname':type}) for _ in range(length)]
        else:
            vars =[self._generate(type, context, recursion_depth+1, force_nonrecursive) for _ in range(length)]
        return '[{}]'.format(','.join(vars))



    def _generate(self, symbol, context,
                  recursion_depth=0, force_nonrecursive=False, script_type=None):
        """Generates a user-defined symbol.

        Selects a rule for the given symbol and resolves the right-hand side
        of the rule.

        Args:
            symbol: The name of the symbol that is being resolved.
            context: dictionary consisting of:
                'lastvar': Index of last variable created.
                'lines': Generated lines of code
                    (for programming language generation).
                'variables': A dictionary containing the names of all
                    variables created so far.
            recursion_depth: Current recursion depth
            force_nonrecursive: Whether to force the use of only
                non-recursive rules.

        Returns:
            A string containing the expansion of the symbol.

        Raises:
            GrammarError: If grammar description is incorrect causing
                some rules being impossible to resolve
            RecursionError: If maximum recursion level was reached.
        """

        # print symbol

        # print 'Expanding ' + symbol + ' in depth ' + str(recursion_depth)

        force_var_reuse = context['force_var_reuse']

        # Check if we already have a variable of the given type.
        if (symbol in context['variables'] and
                symbol not in _NONINTERESTING_TYPES):
            # print symbol + ':' + str(len(context['variables'][symbol])) + ':' + str(force_var_reuse)
            if (symbol not in self._creators or
                    force_var_reuse or
                    random.random() < self._var_reuse_prob or
                    len(context['variables'][symbol]) > self._max_vars_of_same_type):
                # print 'reusing existing var of type ' + symbol
                context['force_var_reuse'] = False
                variables = context['variables'][symbol]
                return variables[random.randint(0, len(variables) - 1)]
                # print 'Not reusing existing var of type ' + symbol

        creator = self._select_creator(
            symbol,
            recursion_depth,
            force_nonrecursive
        )
        return self._expand_rule(
            symbol,
            creator,
            context,
            recursion_depth,
            force_nonrecursive,
            script_type=script_type
        )

    def _expand_rule(self, symbol, rule, context,
                     recursion_depth, force_nonrecursive, variable_ids=None, script_type=None):
        """Expands a given rule.

        Iterates through all the elements on right-hand side of the rule,
        replacing them with their string representations or recursively
        calling _Generate() for other non-terminal symbols.

        Args:
            symbol: The name of the symbol that is being resolved.
            rule: production rule that will be used to expand the symbol.
            context: dictionary consisting of:
                'lastvar': Index of last variable created.
                'lines': Generated lines of code
                    (for programming language generation).
                'variables': A dictionary containing the names of all
                    variables created so far.
            recursion_depth: Current recursion depth
            force_nonrecursive: Whether to force the use of only
                non-recursive rules.

        Returns:
            A string containing the expansion of the symbol.

        Raises:
            GrammarError: If grammar description is incorrect causing
                some rules being impossible to resolve
            RecursionError: If maximum recursion level was reached.
        """
        if variable_ids is None:
            variable_ids = {}

        # Resolve the right side of the rule
        new_vars = []
        ret_vars = []
        ret_parts = []
        append_lines=[]

        arg_parts = []
        for part_idx in range(len(rule['parts'])):
            part = rule['parts'][part_idx]
            is_last_part = (part_idx == len(rule['parts'])-1)
            if "optional" in part and random.random() > self._attr_optional_prob:
                if 'beforeoutput' in part:
                    expanded = self._exec_function(part['beforeoutput'], part, context, '')
                    ret_parts.append(expanded)
            else:
                loop_times = 1
                joinstr = None
                if 'loop' in part:
                    loop_times = int(part['loop'])
                    if 'joinstr' in part:
                        joinstr = part['joinstr']
                elif 'minloop' in part and 'maxloop' in part:
                    minloop = int(part['minloop'])
                    maxloop = int(part['maxloop'])
                    loop_times = random.randint(minloop, maxloop)
                    if 'joinstr' in part:
                        joinstr = part['joinstr']

                for _loop_times_ in range(loop_times):

                    if joinstr is not None and _loop_times_ != 0:
                        ret_parts.append(joinstr)

                    if 'id' in part and part['id'] in variable_ids:
                        expanded = variable_ids[part['id']]
                    elif part['type'] == 'text':
                        expanded = part['text']
                    elif rule['type'] == 'code' and 'new' in part:
                        var_type = part['tagname']
                        context['lastvar'] += 1
                        var_name = self._var_format % context['lastvar']
                        if var_type != "array" or part['elemtype'] in _NONINTERESTING_TYPES:
                            new_vars.append({'name': var_name, 'type': var_type})
                            if var_type == symbol:
                                ret_vars.append(var_name)
                        else:
                            # extract two new variable from the returned array.
                            for _arr_times in range(2):
                                context['lastvar'] += 1
                                element_name = self._var_format % context['lastvar']
                                if script_type == 'vba':
                                    # 'append_lines.append('Set ' + element_name + '={}[{:d}%{}.length]'.format(var_name, random.randint(1000, 10000), var_name))'
                                    append_lines.append('' + element_name + '={}[{:d}%{}.length]'.format(var_name, random.randint(1000, 10000), var_name))
                                else:
                                    append_lines.append('/* newvar{' + element_name + ':' + part['elemtype'] + '} */ var ' +
                                                    element_name + '={}[{:d}%{}.length]'.format(var_name, random.randint(1000, 10000), var_name))
                                new_vars.append({'name': element_name, 'type': part['elemtype']})
                                if part['elemtype'] == symbol:
                                    ret_vars.append(element_name)
                        if script_type == 'vba':
                            # expanded = 'Set ' + var_name
                            expanded = '' + var_name
                        else:
                            expanded = '/* newvar{' + var_name + ':' + var_type + '} */ var ' + var_name
                        if 'id' in part:
                            variable_ids[part['id']] = var_name
                    elif part['tagname'] in self._constant_types:
                        expanded = self._constant_types[part['tagname']]
                    elif part['tagname'] in self._built_in_types:
                        expanded = self._built_in_types[part['tagname']](part)
                    elif part['tagname'] == 'call':
                        if 'function' not in part:
                            raise GrammarError('Call tag without a function attribute')
                        expanded = self._exec_function(part['function'], part, context, '')
                    elif 'array' == part['tagname']:
                        try:
                            expanded = self._generate_array(part, context, recursion_depth + 1, force_nonrecursive)
                        except RecursionError as e:
                            if not force_nonrecursive:
                                expanded = self._generate_array(part, context, recursion_depth + 1, True)
                            else:
                                raise RecursionError(e)
                    else:
                        try:
                            expanded = self._generate(part['tagname'], context, recursion_depth + 1, force_nonrecursive, script_type=script_type)
                        except RecursionError as e:
                            if not force_nonrecursive:
                                expanded = self._generate(part['tagname'], context, recursion_depth + 1, True, script_type=script_type)
                            else:
                                raise RecursionError(e)

                    if 'id' in part and part['id'] not in variable_ids:
                        variable_ids[part['id']] = expanded
                    if 'beforeoutput' in part:
                        expanded = self._exec_function(part['beforeoutput'], part, context, expanded)
                    if "format" in part:
                        expanded = part["format"].format(expanded)
                    if 'arg' in part and script_type == 'vba':
                        arg_parts.append(expanded)
                        if is_last_part and len(arg_parts)>0:
                            ret_parts.append(' , '.join(arg_parts))
                            arg_parts = []
                    else:
                        if len(arg_parts)>0 and script_type == 'vba':
                            ret_parts.append(' , '.join(arg_parts))
                            arg_parts = []
                        ret_parts.append(expanded)

        # Add all newly created variables to the context
        additional_lines = []
        if script_type is None:
            for v in new_vars:
                if v['type'] not in _NONINTERESTING_TYPES:
                    self._add_variable(v['name'], v['type'], context)
                    additional_lines.append("if (!" + v['name'] + ") { " + v['name'] + " = GetVariable(fuzzervars, '" + v['type'] + "'); } else { " + self._get_variable_setters(v['name'], v['type']) + " }")

        # Return the result.
        # In case of 'ordinary' grammar rules, return the filled rule.
        # In case of code, return just the variable name
        # and update the context
        filed_rule = ''.join(ret_parts)
        if rule['type'] == 'grammar':
            return filed_rule
        else:
            context['lines'].append(filed_rule)
            context['lines'].extend(append_lines)
            context['lines'].extend(additional_lines)
            if symbol == 'line':
                return filed_rule
            else:
                return ret_vars[random.randint(0, len(ret_vars) - 1)]

    def generate_root(self):
        """Expands root symbol."""
        if self._root:
            context = {
                'lastvar': 0,
                'lines': [],
                'variables': {},
                'force_var_reuse': False
            }
            return self._generate(self._root, context, 0)
        else:
            print('Error: No root element defined.')
            return ''

    def generate_symbol(self, name):
        """Expands a symbol whose name is given as an argument."""
        context = {
            'lastvar': 0,
            'lines': [],
            'variables': {},
            'force_var_reuse': False
        }
        return self._generate(name, context, 0)

    def _get_cdf(self, symbol, creators):
        """Computes a probability function for a given creator array."""
        uniform = True
        probabilities = []
        defined = []
        cdf = []

        if symbol == 'line':
            # We can't currently set line probability
            return []

        # Get probabilities for individual rule
        for creator in creators:
            if creator['type'] == 'grammar':
                create_tag = creator['creates']
            else:
                # For type=code multiple variables may be created
                for tag in creator['creates']:
                    if tag['tagname'] == symbol or ('array' == tag['tagname'] and tag['elemtype'] ==symbol):
                        create_tag = tag
                        break
            if 'p' in create_tag:
                probabilities.append(float(create_tag['p']))
                defined.append(True)
                uniform = False
            else:
                probabilities.append(0)
                defined.append(False)

        if uniform:
            return []

        # Compute probabilities for rules in which they are not
        # explicitly defined
        # Also normalize probabilities in cases where sum > 1
        nondef_value = 0
        norm_factor = 1.0
        p_sum = sum(probabilities)
        nondef_count = defined.count(False)
        if p_sum > 1 or nondef_count == 0:
            norm_factor = 1.0 / p_sum
        else:
            nondef_value = (1 - p_sum) / nondef_count
        p_sum = 0
        for i in range(len(probabilities)):
            p = probabilities[i]
            if not defined[i]:
                p = nondef_value
            else:
                p *= norm_factor
            p_sum += p
            cdf.append(p_sum)

        return cdf

    def _normalize_probabilities(self):
        """Preprocessess probabilities for production rules.

        Creates CDFs (cumulative distribution functions) and normalizes
        probabilities in the [0,1] range for all creators. This is a
        preprocessing function that makes subsequent creator selection
        based on probability easier.
        """
        for symbol, creators in self._creators.items():
            cdf = self._get_cdf(symbol, creators)
            self._creator_cdfs[symbol] = cdf

        for symbol, creators in self._nonrecursive_creators.items():
            cdf = self._get_cdf(symbol, creators)
            self._nonrecursivecreator_cdfs[symbol] = cdf

    def _parse_tag_and_attributes(self, string):
        """Extracts tag name and attributes from a string."""
        parts = string.split()
        if len(parts) < 1:
            raise GrammarError('Empty tag encountered')
        ret = {'type': 'tag'}
        if len(parts) > 1 and parts[0] == 'new':
            ret['tagname'] = parts[1]
            ret['new'] = 'true'
            attrstart = 2
        else:
            ret['tagname'] = parts[0]
            attrstart = 1
        for i in range(attrstart, len(parts)):
            attrparts = parts[i].split('=')
            if len(attrparts) == 2:
                ret[attrparts[0]] = attrparts[1]
            elif len(attrparts) == 1:
                ret[attrparts[0]] = True
            else:
                raise GrammarError('Error parsing tag ' + string)
        return ret

    def _parse_block_line(self, line):
        """Parses a rule for generating code."""
        clean_line = line.strip()
        match = re.match(r'^:([a-zA-Z0-9_.]+)\s+(.*)$', clean_line)
        if match:
            cmd, params = match.group(1), match.group(2)
            if cmd in self._block_action_handlers:
                action = {
                    'type': 'action',
                    'action': cmd,
                    'parts': self._parse_block_line(params)
                }
                assert action['parts']['type'] == 'code'
                return action
            else:
                assert False and 'Unknown cmd'

        rule = {
            'type': 'code',
            'parts': [],
            'creates': []
        }
        # Splits the line into constant parts and tags. For example
        # "foo<bar>baz" would be split into three parts, "foo", "bar" and "baz"
        # Every other part is going to be constant and every other part
        # is going to be a tag, always starting with a constant. Empty
        # spaces between tags/beginning/end are not a problem because
        # then empty strings will be returned in corresponding places,
        # for example "<foo><bar>" gets split into "", "foo", "", "bar", ""
        rule_parts = re.split(r'<([^>)]*)>', line)
        for i in range(0, len(rule_parts)):
            if i % 2 == 0:
                if rule_parts[i]:
                    rule['parts'].append({
                        'type': 'text',
                        'text': rule_parts[i]
                    })
            else:
                parsedtag = self._parse_tag_and_attributes(rule_parts[i])
                if parsedtag['tagname'] == 'prerun':
                    prerun_times = int(parsedtag['times'])
                    rule['prerun'] = prerun_times if prerun_times < 30 else 30
                    continue
                elif parsedtag['tagname'] == 'repetition':
                    repetition_times = int(parsedtag['times'])
                    rule['repetition'] = repetition_times if repetition_times < 20 else 20
                    continue
                elif parsedtag['tagname'] == 'noguard':
                    rule['noguard'] = True
                    continue
                rule['parts'].append(parsedtag)
                if 'new' in parsedtag:
                    rule['creates'].append(parsedtag)
        return rule

    def _parse_code_line(self, line, helper_lines=False):
        """Parses a rule for generating code."""
        rule = {
            'type': 'code',
            'parts': [],
            'creates': []
        }
        # Splits the line into constant parts and tags. For example
        # "foo<bar>baz" would be split into three parts, "foo", "bar" and "baz"
        # Every other part is going to be constant and every other part
        # is going to be a tag, always starting with a constant. Empty
        # spaces between tags/beginning/end are not a problem because
        # then empty strings will be returned in corresponding places,
        # for example "<foo><bar>" gets split into "", "foo", "", "bar", ""
        rule_parts = re.split(r'<([^>)]*)>', line)
        for i in range(0, len(rule_parts)):
            if i % 2 == 0:
                if rule_parts[i]:
                    rule['parts'].append({
                        'type': 'text',
                        'text': rule_parts[i]
                    })
            else:
                parsedtag = self._parse_tag_and_attributes(rule_parts[i])
                if parsedtag['tagname'] == 'prerun':
                    prerun_times = int(parsedtag['times'])
                    rule['prerun'] = prerun_times if prerun_times < 30 else 30
                    continue
                elif parsedtag['tagname'] == 'repetition':
                    repetition_times = int(parsedtag['times'])
                    rule['repetition'] = repetition_times if repetition_times < 20 else 20
                    continue
                rule['parts'].append(parsedtag)
                if 'new' in parsedtag:
                    rule['creates'].append(parsedtag)

        for tag in rule['creates']:
            tag_name = tag['tagname']
            if tag_name == "array":
                tag_name = tag['elemtype']
            if tag_name in _NONINTERESTING_TYPES:
                continue
            if tag_name in self._creators:
                self._creators[tag_name].append(rule)
            else:
                self._creators[tag_name] = [rule]
            if 'nonrecursive' in tag:
                if tag_name in self._nonrecursive_creators:
                    self._nonrecursive_creators[tag_name].append(rule)
                else:
                    self._nonrecursive_creators[tag_name] = [rule]

        if not helper_lines:
            if 'line' in self._creators:
                self._creators['line'].append(rule)
            else:
                self._creators['line'] = [rule]

        self._all_rules.append(rule)

    def _parse_grammar_line(self, line):
        """Parses a grammar rule."""
        # Check if the line matches grammar rule pattern (<tagname> = ...).
        match = re.match(r'^<([^>]*)>\s*=\s*(.*)$', line)
        if not match:
            raise GrammarError('Error parsing rule ' + line)

        # Parse the line to create a grammar rule.
        rule = {
            'type': 'grammar',
            'creates': self._parse_tag_and_attributes(match.group(1)),
            'parts': []
        }
        rule_parts = re.split(r'<([^>)]*)>', match.group(2))
        rule['recursive'] = False
        # Splits the line into constant parts and tags. For example
        # "foo<bar>baz" would be split into three parts, "foo", "bar" and "baz"
        # Every other part is going to be constant and every other part
        # is going to be a tag, always starting with a constant. Empty
        # spaces between tags/beginning/end are not a problem because
        # then empty strings will be returned in corresponding places,
        # for example "<foo><bar>" gets split into "", "foo", "", "bar", ""
        for i in range(0, len(rule_parts)):
            if i % 2 == 0:
                if rule_parts[i]:
                    rule['parts'].append({
                        'type': 'text',
                        'text': rule_parts[i]
                    })
            else:
                parsedtag = self._parse_tag_and_attributes(rule_parts[i])
                rule['parts'].append(parsedtag)
                if parsedtag['tagname'] == rule['creates']['tagname']:
                    rule['recursive'] = True

        # Store the rule in appropriate sets.
        create_tag_name = rule['creates']['tagname']
        if create_tag_name == "array":
            create_tag_name = rule["creates"]["elemtype"]
        if create_tag_name in self._creators:
            self._creators[create_tag_name].append(rule)
        else:
            self._creators[create_tag_name] = [rule]
        if 'nonrecursive' in rule['creates']:
            if create_tag_name in self._nonrecursive_creators:
                self._nonrecursive_creators[create_tag_name].append(rule)
            else:
                self._nonrecursive_creators[create_tag_name] = [rule]
        self._all_rules.append(rule)
        if 'root' in rule['creates']:
            self._root = create_tag_name

    def _remove_comments(self, line):
        """Removes comments and trims the line."""
        if '#' in line:
            cleanline = line[:line.index('#')].strip()
        else:
            cleanline = line.strip()
        return cleanline

    def _fix_idents(self, source):
        """Fixes indentation in user-defined functions.

        Exec requires zero first-level indentation. This function fixes
        it by finding a minimum indentation in code and removing it
        from all lines.

        Args:
            source: Python source code, possibly with > 0 min indentation.

        Returns:
            Source code with 0 first-level indentation.
        """

        # Tab is 8 spaces according to Python documentation.
        lines = source.replace('\t', ' ' * 8).splitlines()
        lines_without_blanks = [line for line in lines if line.strip()]
        indent_to_remove = min([len(line) - len(line.strip())
                                for line in lines_without_blanks])

        if indent_to_remove == 0:
            return source

        output = []
        for ln in lines:
            if ln.strip():
                ln = ln[indent_to_remove:]
            output.append(ln)

        return '\n'.join(output)

    def _save_function(self, name, source):
        source = self._fix_idents(source)
        try:
            compiled_fn = compile(source, name, 'exec')
        except (SyntaxError, TypeError) as e:
            raise GrammarError('Error in user-defined function: %s' % str(e))
        self._functions[name] = compiled_fn

    def _save_block(self, name, params, body):
        rules = []
        for line in body:
            rules.append(self._parse_block_line(line))
        self._blocks[name] = params, rules

    def _set_variable_format(self, var_format):
        """Sets variable format for programming language generation."""
        self._var_format = var_format.strip()
        return 0

    def _set_line_guard(self, lineguard):
        """Sets a guard block for programming language generation."""
        self._line_guard = lineguard

    def _set_recursion_depth(self, depth_str):
        """Sets maximum recursion depth."""
        depth_str = depth_str.strip()
        if depth_str.isdigit():
            self._recursion_max = int(depth_str)
        else:
            raise GrammarError('Argument to max_recursion is not an integer')

    def _set_var_reuse_probability(self, p_str):
        p_str = p_str.strip()
        try:
            p = float(p_str)
        except ValueError:
            raise GrammarError('Argument to var_reuse_prob is not a number')
        self._var_reuse_prob = p

    def _set_extends(self, p_str):
        args = p_str.strip().split(' ')
        objectname = args[0]
        parentname = args[1]
        if objectname not in self._inheritance:
            self._inheritance[objectname] = []
        # print(objectname, parentname)
        self._inheritance[objectname].append(parentname)

    def _import_grammar(self, filename):
        """Imports a grammar from another file."""
        basename = os.path.basename(filename)
        path = os.path.join(self._definitions_dir, filename)
        subgrammar = Grammar()
        num_errors = subgrammar.parse_from_file(path)
        if num_errors:
            raise GrammarError('There were errors when parsing ' + filename)
        self._imports[basename] = subgrammar

    def add_import(self, name, grammar):
        """Adds a grammar that can then be used from <import> tags.

        In case the grammar is already loaded this can be faster than
        using the !import directive which parses the file again.

        Args:
            name: Name under which to import the grammar.
            grammar: The grammar object to use as import
        """

        self._imports[name] = grammar

    def _include_from_string(self, grammar_str):
        in_code = False
        helper_lines = False
        in_function = False
        in_block = False
        num_errors = 0
        lines = grammar_str.split('\n')
        for line in lines:

            if not in_function:
                cleanline = self._remove_comments(line)
                if not cleanline:
                    continue
            else:
                cleanline = line

            # Process special commands
            match = re.match(r'^!([a-z_]+)\s*(.*)$', cleanline)
            if match:
                command = match.group(1)
                params = match.group(2)
                if command in self._command_handlers:
                    self._command_handlers[command](params)
                elif command == 'begin' and params == 'lines':
                    in_code = True
                    helper_lines = False
                elif command == 'begin' and params == 'helperlines':
                    in_code = True
                    helper_lines = True
                elif command == 'end' and params in ('lines', 'helperlines'):
                    if in_code:
                        in_code = False
                elif command == 'begin' and params.startswith('function'):
                    match = re.match(r'^function\s*([a-zA-Z._0-9]+)$', params)
                    if match and not in_function:
                        function_name = match.group(1)
                        function_body = ''
                        in_function = True
                    else:
                        print('Error parsing line ' + line)
                        num_errors += 1
                elif command == 'end' and params == 'function':
                    if in_function:
                        in_function = False
                        self._save_function(function_name, function_body)
                elif command == 'begin' and params.startswith('block'):
                    match = re.match(r'^block\s*([a-zA-Z._0-9]+)\s*(.*)$', params)
                    if match and not in_block:
                        block_name = match.group(1)
                        block_params = match.group(2).split(' ')
                        block_body = []
                        in_block = True
                elif command == 'end' and params == 'block':
                    if in_block:
                        in_block = False
                        self._save_block(block_name, block_params, block_body)
                else:
                    print('Unknown command: ' + command)
                    num_errors += 1
                continue

            try:
                if in_function:
                    function_body += cleanline + '\n'
                elif in_block:
                    block_body.append(cleanline)
                elif in_code:
                    self._parse_code_line(cleanline, helper_lines)
                else:
                    self._parse_grammar_line(cleanline)
            except GrammarError:
                print('Error parsing line ' + line)
                num_errors += 1
        # random self._all_prerun_lines
        #random.shuffle(self._all_prerun_lines)
        return num_errors

    def _include_from_file(self, filename):
        try:
            f = open(os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                filename
            ))
            content = f.read()
            f.close()
        except IOError:
            print('Error reading ' + filename)
            return 1
        self._definitions_dir = os.path.dirname(filename)
        return self.parse_from_string(content)

    def parse_from_string(self, grammar_str):
        """Parses grammar rules from string.

        Splits the string into lines, parses the lines and loads grammar rules.
        See readme for the rule syntax.

        Args:
            grammar_str: String containing the grammar.

        Returns:
            Number of errors encountered during the parsing.
        """
        errors = self._include_from_string(grammar_str)
        if errors:
            return errors

        return 0

    def parse_from_file(self, filename):
        """Parses grammar from file.

        Opens a text file, parses it and loads the grammar rules within.
        See readme for the rule syntax. Note that grammar
        files can include other grammar files using !import command.

        Args:
            filename: path to the file with grammar rules.

        Returns:
            Number of errors encountered during the parsing.
        """
        try:
            f = open(filename)
            content = f.read()
            f.close()
        except IOError:
            print('Error reading ' + filename)
            return 1
        self._definitions_dir = os.path.dirname(filename)
        err = self.parse_from_string(content)
        self._normalize_probabilities()
        self._compute_interesting_indices()
        return err

#     select indices from self._creators['line'] list that is interesting(the rule is a tag and interesting), and
#     save these indices into self._interesting_lines[tagname] list
    def _compute_interesting_indices(self):
        # select interesting lines for each variable type

        if 'line' not in self._creators:
            return

        for i in range(len(self._creators['line'])):
            rule = self._creators['line'][i]
            if 'repetition' not in rule:
                self._all_nonhelper_lines.append(i)
            else:
                self._all_nonhelper_lines.extend([i]*rule['repetition'])

            if 'prerun' in rule:
                self._all_prerun_lines.extend([i]*rule['prerun'])

            for part in rule['parts']:
                if part['type'] == 'text':
                    continue
                tagname = part['tagname']
                if tagname in _NONINTERESTING_TYPES:
                    continue
                if 'new' in part:
                    continue
                if tagname not in self._interesting_lines:
                    self._interesting_lines[tagname] = []
                self._interesting_lines[tagname].append(i)

    def _add_variable(self, var_name, var_type, context):
        if var_type not in context['variables']:
            context['variables'][var_type] = []
            if var_type in self._interesting_lines:
                set1 = set(context['interesting_lines'])
                set2 = set(self._interesting_lines[var_type])
                new_interesting = set2 - set1
                context['interesting_lines'] += list(new_interesting)
        context['variables'][var_type].append(var_name)
        if var_type in self._inheritance:
            for parent_type in self._inheritance[var_type]:
                self._add_variable(var_name, parent_type, context)

    def _get_variable_setters(self, var_name, var_type):
        ret = "SetVariable(fuzzervars, " + var_name + ", '" + var_type + "'); "
        if var_type in self._inheritance:
            for parent_type in self._inheritance[var_type]:
                ret += self._get_variable_setters(var_name, parent_type)
        return ret
