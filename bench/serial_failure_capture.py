"""Failure-only unittest events for the delivery profiler's owned subprocesses.

No exception text, subtest values, command arguments or arbitrary output is read.
The startup shim is ephemeral; native commands and existing startup hooks remain.
"""
import atexit
from functools import wraps
import json
import os
from pathlib import Path
import re
import sys
import types


def startup(config_path):
    config = json.loads(Path(config_path).read_text())
    original = sys.orig_argv
    owner = Path(config['owner'])
    if len(original) > 1 and original[1] == config['verifier']:
        try:
            with owner.open('x') as stream:
                stream.write(str(os.getpid()))
        except FileExistsError:
            pass
        return
    if original[1:3] != ['-m', 'unittest'] or Path.cwd().resolve() != Path(config['root']):
        return
    try:
        if int(owner.read_text()) != os.getppid():
            return
    except (OSError, ValueError):
        return
    installed = installed_capture(config)
    state = installed.__enter__()

    def finish():
        try:
            Path(config['output']).write_text(json.dumps(state))
        except OSError:
            pass
        finally:
            installed.__exit__(None, None, None)
    atexit.register(finish)


def installed_capture(config, *, detailed=False, target=None, runner=None, receipt=None):
    """Enter shared capture explicitly; importing this helper has no new hooks."""
    from contextlib import contextmanager
    if detailed and target is not None:
        return contextmanager(_standalone_capture)(config, detailed=detailed,
            target=target, runner=runner, receipt=receipt)
    return contextmanager(_capture_events)(config, detailed=detailed, target=target)


def _capture_events(config, *, detailed=False, target=None):
    """Preserve the native serial callback and receipt seam."""
    # Native serial startup reaches this only after command/owner eligibility.
    import unittest
    native_phases = {}
    subprocess = None
    if detailed:
        import subprocess
        fields = type.__dict__['__dict__'].__get__(unittest.TestCase, type(unittest.TestCase))
        for name, phase in (('_callSetUp', 'setup'), ('_callTestMethod', 'test'),
                            ('_callTearDown', 'teardown'), ('_callCleanup', 'cleanup')):
            function = fields.get(name)
            if type(function) is types.FunctionType:
                native_phases[function.__code__] = phase
    state, capture = _metadata_capture(config, detailed=detailed,
        unittest=unittest, subprocess=subprocess, legacy_phases=native_phases,
        exception_classifier=_exception_classifier(subprocess) if detailed else None)
    if detailed:
        state['unsupported_callbacks'] = []

    def native_metadata(callback):
        # Exact Python functions expose these fields through trusted slots.
        # Callable objects can implement arbitrary metadata getters; leave the
        # wrapper undecorated and never inspect their attributes or mappings.
        if type(callback) is types.FunctionType:
            return wraps(callback, updated=())
        return lambda wrapper: wrapper

    # Save raw attributes, including descriptor objects, without a class-level
    # __get__ call. Restore local presence as well as the original value.
    dictionary = type.__dict__['__dict__']
    hierarchy = type.__dict__['__mro__']
    result_type = unittest.TextTestResult if target is None else target
    local = dictionary.__get__(result_type, type(result_type))
    originals = {}
    local_names = set()
    for name in ('addFailure', 'addError', 'addSubTest'):
        if name in local:
            local_names.add(name)
        for base in hierarchy.__get__(result_type, type(result_type)):
            fields = dictionary.__get__(base, type(base))
            if name in fields:
                originals[name] = fields[name]
                break

    def native_binding(callback, instance, owner):
        cls = type(callback)
        for base in hierarchy.__get__(cls, type(cls)):
            fields = dictionary.__get__(base, type(base))
            if '__get__' in fields:
                # Native descriptor lookup takes the raw slot from its class,
                # then passes the descriptor itself, instance and owner.
                # This executes only the actual native binding operation,
                # never a callable's evidence/metadata getters.
                return fields['__get__'](callback, instance, owner)
        return callback

    class CapturedCallback:
        # Preserve the original descriptor at both native access boundaries.
        # Resolve binding once on access, then forward the invocation unchanged.
        def __init__(self, name, callback):
            self.name = name
            self.callback = callback

        def __get__(self, instance, owner):
            callback = self.callback
            native = native_binding(callback, instance, owner)
            if not callable(native):
                return native

            @native_metadata(callback)
            def invoke(*args, **kwargs):
                result_instance = instance
                evidence_args = args
                # A class-accessed exact function receives explicit result self.
                # Other native shapes retain their own arguments and binding.
                if instance is None and type(callback) is types.FunctionType:
                    result_instance = args[0] if args else kwargs.get('self')
                    evidence_args = args[1:] if args else args
                test = evidence_args[0] if evidence_args else kwargs.get('test')
                offset = 2 if self.name == 'addSubTest' else 1
                err = evidence_args[offset] if len(evidence_args) > offset else kwargs.get('err')
                if self.name != 'addSubTest':
                    capture(test, err, 'failed' if self.name == 'addFailure' else 'error')
                    return native(*args, **kwargs)
                if err is None:
                    return native(*args, **kwargs)
                fields = plain_fields(result_instance, unittest.TestResult)
                errors = fields.get('errors') if fields is not None else None
                errors_before = len(errors) if type(errors) is list else None
                event = capture(test, err, 'unknown') if errors_before is not None else None
                result = native(*args, **kwargs)
                if errors_before is None or fields.get('errors') is not errors:
                    state['unmatched_events'] += 1
                    return result
                if event is not None:
                    event['outcome'] = 'error' if len(errors) > errors_before else 'failed'
                return result

            return invoke

    def original_protocol(callback):
        slots = {}
        for base in hierarchy.__get__(type(callback), type(type(callback))):
            fields = dictionary.__get__(base, type(base))
            for name in ('__get__', '__set__', '__delete__'):
                if name not in slots and name in fields:
                    slots[name] = fields[name]
        return slots

    def callback_wrapper(name, callback, slots):
        # Precedence is selected by the wrapper TYPE's descriptor slots.
        # Only mirror slots that the original type actually provides.
        attributes = {}
        if '__set__' in slots:
            setter = slots['__set__']
            def set_value(self, instance, value):
                return setter(callback, instance, value)
            attributes['__set__'] = set_value
        if '__delete__' in slots:
            deleter = slots['__delete__']
            def delete_value(self, instance):
                return deleter(callback, instance)
            attributes['__delete__'] = delete_value
        wrapper_type = type('CapturedNativeCallback', (CapturedCallback,), attributes)
        return wrapper_type(name, callback)

    installed = {}
    try:
        for name, callback in originals.items():
            slots = original_protocol(callback)
            if '__get__' not in slots:
                # No native access interposition point: preserve the raw object.
                # No event or count is manufactured for unobserved invocations.
                if detailed:
                    state['unsupported_callbacks'].append(name)
                continue
            wrapper = callback_wrapper(name, callback, slots)
            installed[name] = wrapper
            setattr(result_type, name, wrapper)
        yield state
    finally:
        current = dictionary.__get__(result_type, type(result_type))
        for name, wrapper in installed.items():
            # User deletion or reassignment is native state and survives exit.
            if current.get(name) is not wrapper:
                continue
            if name in local_names:
                setattr(result_type, name, originals[name])
            else:
                delattr(result_type, name)


def plain_fields(value, base):
    # Invoke only the trusted stdlib descriptor, never a user property/get.
    try:
        dictionary = type.__dict__['__dict__']
        hierarchy = type.__dict__['__mro__']
        for parent in hierarchy.__get__(base, type(base)):
            fields = dictionary.__get__(parent, type(parent))
            if '__dict__' in fields:
                descriptor = fields['__dict__']
                if type(descriptor) is not types.GetSetDescriptorType:
                    return None
                fields = descriptor.__get__(value, type(value))
                return fields if type(fields) is dict else None
        return None
    except (TypeError, AttributeError):
        return None


def _exception_classifier(subprocess):
    """Fixed labels from immutable builtins and source-equivalent stdlib CPE.

    Validate public aliases at explicit detailed entry, then require live alias
    agreement. Unsupported thrown classes and objects are never queried.
    Source equivalence is a behavior classification, not historical provenance.
    """
    import builtins
    import sysconfig
    slots = type.__dict__
    dictionary = slots['__dict__']
    bases = slots['__bases__']
    labels = ('AssertionError', 'RuntimeError', 'ValueError', 'TypeError',
              'KeyError', 'IndexError', 'OSError', 'PermissionError',
              'FileNotFoundError', 'ImportError', 'ModuleNotFoundError',
              'AttributeError', 'ZeroDivisionError')
    def builtin(label):
        # Invoke the immutable ModuleType slot, bypassing subclass getters.
        fields = types.ModuleType.__dict__['__dict__'].__get__(builtins, type(builtins))
        candidate = dict.get(fields, label) if type(fields) is dict else None
        if type(candidate) is not type:
            return None
        # Reject heap/custom classes before reading any name or dictionary.
        if slots['__flags__'].__get__(candidate, type) & (1 << 9):
            return None
        if (slots['__name__'].__get__(candidate, type) != label
                or slots['__module__'].__get__(candidate, type) != 'builtins'):
            return None
        return candidate
    allowed = [(builtin(label), label) for label in labels]
    native_exception = builtin('Exception')
    native_base_exception = builtin('BaseException')
    native = None
    source_classes = {}
    module_fields = subprocess.__dict__ if type(subprocess) is types.ModuleType else {}
    filename = module_fields.get('__file__')
    # Optional source evidence must not prevent native suite execution. Keep
    # the narrow availability boundary around public path checks/read/compile;
    # fixed builtin classification remains available when CPE proof declines.
    try:
        stdlib = sysconfig.get_path('stdlib')
        expected = Path(stdlib) / 'subprocess.py' if type(stdlib) is str else None
        if (expected is not None and type(filename) is str and Path(filename) == expected
                and not expected.is_symlink()
                and type(module_fields.get('__name__')) is str
                and module_fields['__name__'] == 'subprocess'):
            code = compile(expected.read_text(), filename, 'exec',
                           dont_inherit=True, optimize=sys.flags.optimize)
            source_classes = {c.co_name: c for c in code.co_consts
                              if type(c) is types.CodeType
                              and c.co_name in ('SubprocessError', 'CalledProcessError')}
    except (OSError, UnicodeError, SyntaxError):
        source_classes = {}

    def valid_cpe(candidate):
        if (type(module_fields.get('__name__')) is not str
                or module_fields['__name__'] != 'subprocess'
                or type(module_fields.get('__file__')) is not str
                or module_fields['__file__'] != filename):
            return False
        base = module_fields.get('SubprocessError')
        if (type(candidate) is not type or type(base) is not type
                or native_exception is None or native_base_exception is None
                or len(bases.__get__(candidate, type)) != 1
                or bases.__get__(candidate, type)[0] is not base
                or len(bases.__get__(base, type)) != 1
                or bases.__get__(base, type)[0] is not native_exception
                or set(source_classes) != {'SubprocessError', 'CalledProcessError'}):
            return False
        # Only the public stdlib candidates reach raw descriptor reads; no
        # exception instance/class metadata lookup or metaclass getter is used.
        base_fields = dictionary.__get__(base, type)
        fields = dictionary.__get__(candidate, type)
        if (set(base_fields) != {'__module__', '__weakref__', '__doc__'}
                or type(base_fields['__weakref__']) is not types.GetSetDescriptorType
                or type(base_fields['__module__']) is not str
                or base_fields['__module__'] != 'subprocess' or base_fields['__doc__'] is not None
                or set(fields) != {'__module__', '__doc__', '__init__', '__str__', 'stdout'}
                or type(fields['__module__']) is not str or fields['__module__'] != 'subprocess'
                or type(fields['__doc__']) is not str
                or fields['__doc__'] != source_classes['CalledProcessError'].co_consts[1]):
            return False
        compiled = {c.co_name: c for c in source_classes['CalledProcessError'].co_consts
                    if type(c) is types.CodeType}
        functions = [(fields['__init__'], compiled.get('__init__'), (None, None)),
                     (fields['__str__'], compiled.get('__str__'), None)]
        prop = fields['stdout']
        if type(prop) is not property:
            return False
        stdout_codes = [c for c in source_classes['CalledProcessError'].co_consts
                        if type(c) is types.CodeType and c.co_name == 'stdout']
        if len(stdout_codes) != 2 or prop.fdel is not None:
            return False
        functions.extend(((prop.fget, stdout_codes[0], None),
                          (prop.fset, stdout_codes[1], None)))
        for function, code, defaults in functions:
            if (type(function) is not types.FunctionType or function.__code__ != code
                    or function.__globals__ is not module_fields
                    or function.__closure__ is not None or function.__kwdefaults__ is not None):
                return False
            values = function.__defaults__
            if defaults is None:
                if values is not None:
                    return False
            elif (type(values) is not tuple or len(values) != 2
                  or any(value is not None for value in values)):
                return False
        # These native-source candidates have passed every behavioral check.
        return all(slots[name].__get__(cls, type) == label
                   for cls, label in ((base, 'SubprocessError'), (candidate, 'CalledProcessError'))
                   for name in ('__name__', '__qualname__'))

    candidate = module_fields.get('CalledProcessError')
    if valid_cpe(candidate):
        native = candidate
    def classify(kind, value):
        for candidate, label in allowed:
            if candidate is not None and kind is candidate and builtin(label) is candidate:
                return label, None
        if (native is not None and kind is native and type(value) is native
                and module_fields.get('CalledProcessError') is native and valid_cpe(native)):
            fields = plain_fields(value, native_base_exception)
            returncode = fields.get('returncode') if fields is not None else None
            return 'CalledProcessError', returncode if type(returncode) is int else None
        return 'unknown', None
    return classify


def _metadata_capture(config, *, detailed=False, unittest, subprocess=None,
                      exception_classifier=None,
                      live_phases=None, dispatch_sites=None, legacy_phases=None):
    """Bounded metadata shared by native serial and explicit standalone capture."""
    root = Path(config['root'])
    identities = set(config['identities'])
    sources = set(config['sources'])
    state = {'failed_tests': [], 'matched_events': 0, 'unmatched_events': 0, 'truncated': False}
    holder = re.compile(r'^(?:setUpClass|tearDownClass|setUpModule|tearDownModule) \(([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)\)$')
    def capture(test, error, outcome):
        try:
            if type(error) is not tuple or len(error) != 3:
                state['unmatched_events'] += 1
                return
            # Exact type checks do not ask unsupported objects for __class__.
            # Such tuples can be valid for custom native result callbacks;
            # decline their metadata and still deliver the callback once.
            if error[2] is not None and type(error[2]) is not types.TracebackType:
                state['unmatched_events'] += 1
                return
            cls = type(test)
            identity = None
            fields = None
            phase = 'unknown'
            if type(cls) is type:
                base = unittest.suite._ErrorHolder if cls is unittest.suite._ErrorHolder else unittest.TestCase
                fields = plain_fields(test, base)
                if fields is not None and cls is unittest.suite._ErrorHolder:
                    description = fields.get('description')
                    match = holder.fullmatch(description) if type(description) is str else None
                    identity = match.group(1) if match else None
                    if match:
                        phase = description.split(' ', 1)[0]
                elif fields is not None:
                    method = fields.get('_testMethodName')
                    module = type.__getattribute__(cls, '__dict__').get('__module__')
                    qualname = type.__getattribute__(cls, '__qualname__')
                    if all(type(part) is str for part in (module, qualname, method)):
                        identity = module + '.' + qualname + '.' + method
            if identity not in identities:
                state['unmatched_events'] += 1
                return
            state['matched_events'] += 1
            if len(state['failed_tests']) >= 1024:
                state['truncated'] = True
                return
            frames = []
            module_id = identity.split('.', 1)[0]
            class_id = identity.rsplit('.', 1)[0] if identity.count('.') >= 2 else (
                identity if identity.count('.') == 1 and not identity.startswith('unittest.loader.') else None)
            if identity.startswith('unittest.loader._FailedTest.'):
                module_id = identity.rsplit('.', 1)[1]
                class_id = None
                phase = 'import'
            native_phases, supported_codes = live_phases(cls, fields) if detailed and live_phases is not None else ({}, set())
            observed_roles = set()
            dispatched_roles = set()
            ambiguous_phase = False
            traceback = error[2]
            while type(traceback) is types.TracebackType:
                code = traceback.tb_frame.f_code
                if detailed and dispatch_sites is not None:
                    dispatch = dispatch_sites.get((code, traceback.tb_lasti))
                    if dispatch is not None:
                        dispatched_roles.add(dispatch)
                if detailed and legacy_phases is not None and phase == 'unknown' and code in legacy_phases:
                    phase = legacy_phases[code]
                if detailed and code in native_phases:
                    roles = native_phases[code]
                    if len(roles) != 1 or code not in supported_codes:
                        ambiguous_phase = True
                    else:
                        observed_roles.update(roles)
                filename = code.co_filename
                if type(filename) is not str:
                    traceback = traceback.tb_next
                    continue
                path = Path(filename)
                try:
                    relative = path.resolve().relative_to(root).as_posix()
                except (ValueError, OSError, RuntimeError):
                    relative = None
                # Require the original lexical path too: a symlink into a public
                # file is not an eligible source frame. Inventory is Git-bound.
                if relative in sources and path == root / relative:
                    if len(frames) < 64:
                        frames.append({'file': relative, 'line': traceback.tb_lineno})
                    else:
                        state['truncated'] = True
                traceback = traceback.tb_next
            # subTest delivers only the inner traceback. The active native
            # TestCase caller can prove fixture/test phase without reading locals.
            if detailed and phase == 'unknown':
                frame = sys._getframe()
                for _ in range(64):
                    if frame is None:
                        break
                    code = frame.f_code
                    if dispatch_sites is not None:
                        dispatch = dispatch_sites.get((code, frame.f_lasti))
                        if dispatch is not None:
                            dispatched_roles.add(dispatch)
                    if legacy_phases is not None and code in legacy_phases:
                        phase = legacy_phases[code]
                        break
                    if code in native_phases:
                        roles = native_phases[code]
                        if len(roles) != 1 or code not in supported_codes:
                            ambiguous_phase = True
                        else:
                            observed_roles.update(roles)
                    frame = frame.f_back
                del frame
                if (not ambiguous_phase and len(observed_roles) == 1
                        and observed_roles == dispatched_roles):
                    phase = next(iter(observed_roles))
            event = {'id': identity, 'outcome': outcome, 'source_frames': frames}
            if detailed:
                label, returncode = exception_classifier(error[0], error[1])
                event.update(module_id=module_id, class_id=class_id, phase=phase,
                             exception_type=label)
                if returncode is not None:
                    event['subprocess_returncode'] = returncode
            state['failed_tests'].append(event)
            return event
        except Exception:
            # Evidence must never replace or suppress the native result.
            state['unmatched_events'] += 1

    return state, capture

def _standalone_trust():
    """Compile native source only for explicitly requested standalone capture.

    Code equality classifies source equivalence, not historical provenance.
    """
    import dis
    import unittest
    # Source metadata is optional evidence. Only exact public native modules and
    # exact strings reach Path/compile; never run user getters or PathLike hooks.
    module_dictionary = types.ModuleType.__dict__['__dict__']
    if type(unittest) is not types.ModuleType:
        return None
    public = module_dictionary.__get__(unittest, types.ModuleType)
    modules = {name: dict.get(public, name) for name in ('result', 'runner', 'case')}
    if any(type(module) is not types.ModuleType for module in modules.values()):
        return None
    import sysconfig
    try:
        stdlib = sysconfig.get_path('stdlib')
    except OSError:
        return None
    if type(stdlib) is not str:
        return None
    directory = Path(stdlib) / 'unittest'
    try:
        directory_symlink = directory.is_symlink()
    except OSError:
        return None
    if directory_symlink:
        return None
    source_fields = {}
    for name, module in modules.items():
        fields = module_dictionary.__get__(module, types.ModuleType)
        filename = dict.get(fields, '__file__')
        label = dict.get(fields, '__name__')
        expected = directory / (name + '.py')
        if (type(filename) is not str or type(label) is not str
                or label != 'unittest.' + name or filename != str(expected)):
            return None
        try:
            source_symlink = expected.is_symlink()
        except OSError:
            return None
        if source_symlink:
            return None
        source_fields[name] = (module, fields, filename)

    def _source_available():
        # Recheck live public aliases/metadata without ordinary module lookup.
        if type(unittest) is not types.ModuleType:
            return False
        current = module_dictionary.__get__(unittest, types.ModuleType)
        for name, (module, fields, filename) in source_fields.items():
            if (type(module) is not types.ModuleType or dict.get(current, name) is not module
                    or module_dictionary.__get__(module, types.ModuleType) is not fields
                    or type(dict.get(fields, '__file__')) is not str
                    or dict.get(fields, '__file__') != filename
                    or type(dict.get(fields, '__name__')) is not str
                    or dict.get(fields, '__name__') != 'unittest.' + name):
                return False
        return True

    # Compile the fixed eligible native sources; never execute them again.
    compiled = {}
    for name, (module, fields, filename) in source_fields.items():
        try:
            source = Path(filename).read_text()
            compiled[name] = compile(source, filename, 'exec', dont_inherit=True,
                                     optimize=sys.flags.optimize)
        except (OSError, UnicodeError, SyntaxError):
            return None
    def _class_codes(name, class_name):
        body = next((c for c in compiled[name].co_consts
                     if type(c) is types.CodeType and c.co_name == class_name), None)
        return ({c.co_name: c for c in body.co_consts if type(c) is types.CodeType}
                if body is not None else {})

    _RESULT_CODES = _class_codes('result', 'TestResult')
    _RUNNER_CODES = _class_codes('runner', 'TextTestRunner')
    _TEXT_RESULT_CODES = _class_codes('runner', 'TextTestResult')
    _CASE_CODES = _class_codes('case', 'TestCase')
    for codes, required in (
            (_RESULT_CODES, ('__init__', 'addError', 'addFailure', 'addSubTest')),
            (_RUNNER_CODES, ('_makeResult', 'run')),
            (_TEXT_RESULT_CODES, ('__init__',)),
            (_CASE_CODES, ('run', 'doCleanups', '_callSetUp', '_callTestMethod',
                           '_callTearDown', '_callCleanup'))):
        if any(name not in codes for name in required):
            return None

    # Match source-compiled native dispatcher call sites, including CALL cache slots.
    # A hook's dictionary at formatting time cannot establish historical dispatch.
    def _dispatcher_sites():
        sites = {}
        for name, hooks in (
                ('run', {'_callSetUp': 'setup', '_callTestMethod': 'test',
                         '_callTearDown': 'teardown'}),
                ('doCleanups', {'_callCleanup': 'cleanup'})):
            code = _CASE_CODES[name]
            instructions = list(dis.get_instructions(code, show_caches=True))
            for hook, phase in hooks.items():
                loads = [i for i in instructions
                         if i.opname == 'LOAD_ATTR' and i.argval == hook]
                if len(loads) != 1:
                    continue
                position = loads[0].positions
                calls = [i for i in instructions
                         if i.opname in ('CALL', 'CALL_FUNCTION_EX')
                         and i.positions.lineno == position.lineno
                         and i.positions.col_offset == position.col_offset]
                if len(calls) != 1:
                    continue
                call = calls[0]
                sites[(code, call.offset)] = phase
                for following in instructions[instructions.index(call) + 1:]:
                    if following.opname != 'CACHE':
                        break
                    sites[(code, following.offset)] = phase
        return sites

    _DISPATCH_SITES = _dispatcher_sites()

    def _source_initializer(cls, module, code, defaults, keyword):
        # Read function fields only after an exact supported-type check. Source code,
        # globals and native defaults establish trust; install-time presence does not.
        fields = type.__dict__['__dict__'].__get__(cls, type(cls))
        function = fields.get('__init__')
        if type(function) is not types.FunctionType:
            return None
        if (not _source_available() or type(module) is not types.ModuleType
                or function.__code__ != code
                or function.__globals__ is not module_dictionary.__get__(module, types.ModuleType)):
            return None
        closure = function.__closure__
        if cls is unittest.TextTestResult:
            if code.co_freevars != ('__class__',) or type(closure) is not tuple or len(closure) != 1:
                return None
            cell = closure[0]
            if type(cell) is not types.CellType:
                return None
            try:
                if types.CellType.__dict__['cell_contents'].__get__(cell, types.CellType) is not cls:
                    return None
            except ValueError:
                return None
        elif cls is unittest.TestResult:
            if code.co_freevars != () or closure is not None:
                return None
        else:
            return None
        positional = function.__defaults__
        if defaults:
            if type(positional) is not tuple or len(positional) != defaults or any(x is not None for x in positional):
                return None
        elif positional is not None:
            return None
        keywords = function.__kwdefaults__
        if keyword:
            if type(keywords) is not dict or len(keywords) != 1 or dict.get(keywords, keyword, _MISSING) is not None:
                return None
        elif keywords is not None:
            return None
        return function

    _NATIVE = {_RESULT_CODES[name]: name for name in ('addError', 'addFailure', 'addSubTest')}
    _FRAME_FIELDS = types.FrameType.__dict__
    _FRAME_CODE = _FRAME_FIELDS['f_code']
    _FRAME_BACK = _FRAME_FIELDS['f_back']
    _FRAME_LOCALS = _FRAME_FIELDS['f_locals']
    _MISSING = object()
    _TEXT_INIT = _source_initializer(unittest.TextTestResult, unittest.runner,
                                     _TEXT_RESULT_CODES['__init__'], 0, 'durations')
    _BASE_INIT = _source_initializer(unittest.TestResult, unittest.result,
                                     _RESULT_CODES['__init__'], 3, None)

    return {
        '_RESULT_CODES': _RESULT_CODES, '_RUNNER_CODES': _RUNNER_CODES,
        '_TEXT_RESULT_CODES': _TEXT_RESULT_CODES, '_CASE_CODES': _CASE_CODES,
        '_DISPATCH_SITES': _DISPATCH_SITES, '_source_initializer': _source_initializer,
        '_NATIVE': _NATIVE, '_FRAME_CODE': _FRAME_CODE, '_FRAME_BACK': _FRAME_BACK,
        '_FRAME_LOCALS': _FRAME_LOCALS, '_MISSING': _MISSING,
        '_TEXT_INIT': _TEXT_INIT, '_BASE_INIT': _BASE_INIT,
        '_source_available': _source_available,
    }

def _standalone_capture(config, *, detailed, target, runner, receipt=None):
    """Observe the owned result through its constructor and native formatter.

    The finite supported lane reads only self on two source-bound native frames,
    releases those mappings immediately, and retains no traceback or output.
    Custom construction stays native and unregistered. Saved-callable, audit,
    concurrent and arbitrary-object universality are outside this evidence.
    """
    from contextlib import contextmanager
    import unittest
    state = {'failed_tests': [], 'matched_events': 0, 'unmatched_events': 0,
             'truncated': False, 'unsupported_callbacks': []}
    trust = _standalone_trust()
    if trust is None:
        # No registration or forwarding hooks when native source is unprovable.
        # Empty counts describe unobserved failures; the profiler reports unknown.
        yield state
        return
    import subprocess
    exception_classifier = _exception_classifier(subprocess) if detailed else None
    _RESULT_CODES = trust['_RESULT_CODES']
    _RUNNER_CODES = trust['_RUNNER_CODES']
    _TEXT_RESULT_CODES = trust['_TEXT_RESULT_CODES']
    _CASE_CODES = trust['_CASE_CODES']
    _DISPATCH_SITES = trust['_DISPATCH_SITES']
    _source_initializer = trust['_source_initializer']
    _NATIVE = trust['_NATIVE']
    _FRAME_CODE = trust['_FRAME_CODE']
    _FRAME_BACK = trust['_FRAME_BACK']
    _FRAME_LOCALS = trust['_FRAME_LOCALS']
    _MISSING = trust['_MISSING']
    _TEXT_INIT = trust['_TEXT_INIT']
    _BASE_INIT = trust['_BASE_INIT']
    source_available = trust['_source_available']
    def live_phases(cls, instance_fields):
        # Resolve each callback's effective hooks from trusted raw dictionaries.
        # Aliases keep all roles; unsupported hooks never acquire a native claim.
        roles = {}
        supported_codes = set()
        if (not source_available()
                or unittest.TestCase is not unittest.case.TestCase
                or type(cls) is not type or type(instance_fields) is not dict):
            return roles, supported_codes
        names = ('_callSetUp', '_callTestMethod', '_callTearDown', '_callCleanup')
        if any(name in instance_fields for name in names):
            return roles, supported_codes
        dictionary = type.__dict__['__dict__']
        hierarchy = type.__dict__['__mro__'].__get__(cls, type(cls))
        all_supported = True
        for name, phase in (('_callSetUp', 'setup'), ('_callTestMethod', 'test'),
                            ('_callTearDown', 'teardown'), ('_callCleanup', 'cleanup')):
            function = None
            for base in hierarchy:
                fields = dictionary.__get__(base, type(base))
                if name in fields:
                    function = fields[name]
                    break
            if type(function) is types.FunctionType and type(function.__code__) is types.CodeType:
                code = function.__code__
                roles.setdefault(code, set()).add(phase)
                if (code == _CASE_CODES[name] and function.__globals__ is unittest.case.__dict__
                        and function.__defaults__ is None and function.__kwdefaults__ is None
                        and function.__closure__ is None):
                    supported_codes.add(code)
                else:
                    all_supported = False
            else:
                all_supported = False
        # A descriptor/custom hook may route through another role's native code.
        # No phase is provable from that code alone when effective dispatch differs.
        return (roles, supported_codes) if all_supported else ({}, set())

    def extract(test, error):
        data, capture = _metadata_capture(config, detailed=detailed,
            unittest=unittest, subprocess=subprocess, exception_classifier=exception_classifier,
            live_phases=live_phases,
            dispatch_sites=_DISPATCH_SITES)
        capture(test, error, 'unknown')
        return data

    dictionary = type.__dict__['__dict__']
    hierarchy = type.__dict__['__mro__']
    def raw(cls, name):
        for base in hierarchy.__get__(cls, type(cls)):
            fields = dictionary.__get__(base, type(base))
            if name in fields:
                return fields[name]
        return None

    def supported(name):
        callback = raw(target, name)
        getter = raw(type(callback), '__get__')
        if getter is None:
            if name not in state['unsupported_callbacks']:
                state['unsupported_callbacks'].append(name)
            return False
        return True

    for name in ('addFailure', 'addError', 'addSubTest'):
        supported(name)
    owned = None
    pending = None
    busy = False

    def lists():
        fields = plain_fields(owned, unittest.TestResult)
        if fields is None:
            return None
        errors, failures = fields.get('errors'), fields.get('failures')
        if type(errors) is list and type(failures) is list:
            return errors, failures
        return None

    def reconcile():
        nonlocal pending
        item, pending = pending, None
        if item is None:
            return
        observed = lists()
        matched = False
        outcome = None
        if observed is not None and len(item['lengths']) == 2:
            # Exactly one new native failure occurrence; never parse its text.
            additions = [len(items) - item['lengths'][i] for i, items in enumerate(observed)]
            if additions in ([1, 0], [0, 1]):
                i = additions.index(1)
                row = observed[i][item['lengths'][i]]
                if type(row) is tuple and len(row) == 2:
                    test = row[0]
                    matched = id(test) == item['test_id']
                    if type(test) is unittest.case._SubTest:
                        fields = plain_fields(test, unittest.TestCase)
                        matched = fields is not None and id(fields.get('test_case')) == item['test_id']
                    outcome = 'error' if i == 0 else 'failed'
        data = item['data']
        if not matched or data['matched_events'] != 1:
            state['unmatched_events'] += 1
            return
        state['matched_events'] += 1
        state['truncated'] = state['truncated'] or data['truncated']
        if len(state['failed_tests']) < 1024:
            event = data['failed_tests'][0]
            event['outcome'] = outcome
            state['failed_tests'].append(event)
        else:
            state['truncated'] = True

    active = True

    def note(reason):
        if type(receipt) is list and len(receipt) < 64:
            receipt.append(reason)

    def known_runner():
        # Profiler fills this holder at its unchanged native creation point.
        return runner[0] if type(runner) is list and len(runner) == 1 else runner

    def admit(result, frame):
        nonlocal owned
        parent = local = other = None
        reason = 'unproved-construction'
        try:
            current = known_runner()
            if not active or type(result) is not target or type(target) is not type:
                return
            if type(current) is not unittest.TextTestRunner:
                return
            if raw(target, '__new__') is not object.__new__:
                reason = 'custom-allocation'
                return
            fields = plain_fields(current, unittest.TextTestRunner)
            if fields is None or fields.get('resultclass') is not target:
                return
            if '_makeResult' in fields or 'run' in fields:
                reason = 'custom-runner-call-path'
                return
            if type(frame) is not types.FrameType:
                return
            if _FRAME_CODE.__get__(frame) != _RUNNER_CODES['_makeResult']:
                reason = 'outside-native-factory'
                return
            parent = _FRAME_BACK.__get__(frame)
            if type(parent) is not types.FrameType or _FRAME_CODE.__get__(parent) != _RUNNER_CODES['run']:
                reason = 'outside-direct-native-run'
                return
            # The only locals access is self on these two trusted native frames.
            local = _FRAME_LOCALS.__get__(frame)
            other = _FRAME_LOCALS.__get__(parent)
            if type(local) is not dict or type(other) is not dict:
                return
            if dict.get(local, 'self') is not current or dict.get(other, 'self') is not current:
                reason = 'other-runner'
                return
            if dictionary.__get__(target, type(target)).get('__init__') is not initialize:
                reason = 'constructor-mutated'
                return
            reconcile()
            owned = result
            reason = 'exact-native-run-factory-default-construction'
        except Exception:
            reason = 'unproved-construction'
        finally:
            frame = parent = local = other = None
            note(reason)

    # Existing owned constructor seam. With native local absence, super performs
    # live inherited special-method binding, without an instance metadata lookup.
    initial_init = dictionary.__get__(target, type(target)).get('__init__', _MISSING)
    initial_formatter = dictionary.__get__(target, type(target)).get('_exc_info_to_string', _MISSING)

    def default_inherited_initializer():
        # Raw trusted class dictionaries only: no initializer descriptor binding,
        # getters, callable metadata or unsupported-object evidence inspection.
        if not source_available() or _TEXT_INIT is None or _BASE_INIT is None:
            return False
        inherited = None
        for base in hierarchy.__get__(target, type(target))[1:]:
            fields = dictionary.__get__(base, type(base))
            if '__init__' in fields:
                inherited = fields['__init__']
                break
        return (inherited is _TEXT_INIT and
                dictionary.__get__(unittest.TextTestResult, type(unittest.TextTestResult)).get('__init__') is _TEXT_INIT and
                dictionary.__get__(unittest.TestResult, type(unittest.TestResult)).get('__init__') is _BASE_INIT and
                _source_initializer(unittest.TextTestResult, unittest.runner,
                                    _TEXT_RESULT_CODES['__init__'], 0, 'durations') is _TEXT_INIT and
                _source_initializer(unittest.TestResult, unittest.result,
                                    _RESULT_CODES['__init__'], 3, None) is _BASE_INIT)

    def initialize(self, *args, **kwargs):
        trusted = default_inherited_initializer()
        returned = super(target, self).__init__(*args, **kwargs)
        if returned is None and trusted and default_inherited_initializer():
            frame = None
            try:
                frame = sys._getframe(1)
                admit(self, frame)
            finally:
                frame = None
        return returned

    @contextmanager
    def expose_formatter():
        fields = dictionary.__get__(target, type(target))
        owns = fields.get('_exc_info_to_string', _MISSING) is forwarding
        if owns:
            if initial_formatter is _MISSING:
                type.__delattr__(target, '_exc_info_to_string')
            else:
                type.__setattr__(target, '_exc_info_to_string', initial_formatter)
        try:
            yield
        finally:
            if owns:
                current = dictionary.__get__(target, type(target)).get('_exc_info_to_string', _MISSING)
                if current is initial_formatter:
                    type.__setattr__(target, '_exc_info_to_string', forwarding)

    def invoke(self, native, args, kwargs, caller):
        nonlocal pending, busy
        observing = False
        if active and self is owned and not busy and source_available():
            busy = True
            try:
                reconcile()
                name = _NATIVE.get(caller)
                if name is not None and supported(name):
                    observed = lists()
                    if len(args) == 2 and not kwargs:
                        error, test = args
                        data = extract(test, error)
                        pending = {'test_id': id(test),
                                   'lengths': tuple(len(x) for x in observed) if observed is not None else (),
                                   'data': data}
                        observing = True
            except Exception:
                pending = None
                state['unmatched_events'] += 1
            finally:
                busy = False
        previous_busy, busy = busy, True
        try:
            return native(*args, **kwargs)
        except BaseException:
            if observing:
                pending = None
                state['unmatched_events'] += 1
            raise
        finally:
            busy = previous_busy

    class ForwardingFormatter:
        def __get__(descriptor, instance, owner):
            with expose_formatter():
                native = (type.__getattribute__(owner, '_exc_info_to_string')
                          if instance is None else
                          object.__getattribute__(instance, '_exc_info_to_string'))
            if instance is None or not callable(native):
                return native
            def call(*args, **kwargs):
                frame = None
                try:
                    frame = sys._getframe(1)
                    caller = _FRAME_CODE.__get__(frame)
                finally:
                    frame = None
                return invoke(instance, native, args, kwargs, caller)
            return call

        def __set__(descriptor, instance, value):
            with expose_formatter():
                return object.__setattr__(instance, '_exc_info_to_string', value)

        def __delete__(descriptor, instance):
            with expose_formatter():
                return object.__delattr__(instance, '_exc_info_to_string')

    forwarding = ForwardingFormatter()
    # Custom local construction remains native and unregistered.
    installed_init = initial_init is _MISSING
    if installed_init:
        type.__setattr__(target, '__init__', initialize)
    type.__setattr__(target, '_exc_info_to_string', forwarding)
    try:
        yield state
    finally:
        try:
            reconcile()
        except Exception:
            state['unmatched_events'] += 1
        active = False
        if dictionary.__get__(target, type(target)).get('_exc_info_to_string', _MISSING) is forwarding:
            if initial_formatter is _MISSING:
                type.__delattr__(target, '_exc_info_to_string')
            else:
                type.__setattr__(target, '_exc_info_to_string', initial_formatter)
        if installed_init and dictionary.__get__(target, type(target)).get('__init__', _MISSING) is initialize:
            type.__delattr__(target, '__init__')
        pending = owned = None
