import functools
import re
from typing import Literal

from q2cli.core.usage import CLIUsage
from qiime2.core.type import is_semantic_type, is_visualization_type
from qiime2.plugins import ArtifactAPIUsage, ArtifactAPIUsageVariable
from qiime2.sdk.usage import (
    Usage, UsageAction, UsageInputs, UsageOutputNames, UsageOutputs)

from .util import camel_to_snake


def action(self,
           action: 'UsageAction',
           inputs: 'UsageInputs',
           outputs: 'UsageOutputNames',
           ) -> 'UsageOutputs':
    """
    A monkeypatch for Usage.action that deals with archive versions that don't
    track output-name generously.

    If there no output-name to search the signature with, it will attempt
    to search the signature.outputs for a parameter spec with the same
    QIIME type.

    Because our goal in the patched snippet is to assign a usage example type,
    a type-expression match should always return a correct usage example type.
    """
    if not isinstance(action, UsageAction):  # pragma: no cover
        raise ValueError('Invalid value for `action`: expected %r, '
                         'received %r.' % (UsageAction, type(action)))

    if not isinstance(inputs, UsageInputs):  # pragma: no cover
        raise ValueError('Invalid value for `inputs`: expected %r, '
                         'received %r.' % (UsageInputs, type(inputs)))

    if not isinstance(outputs, UsageOutputNames):  # pragma: no cover
        raise ValueError('Invalid value for `outputs`: expected %r, '
                         'received %r.' % (UsageOutputNames,
                                           type(outputs)))

    action_f = action.get_action()

    @functools.lru_cache(maxsize=None)
    def memoized_action():  # pragma: no cover
        execed_inputs = inputs.map_variables(lambda v: v.execute())
        if self.asynchronous:
            return action_f.asynchronous(**execed_inputs).result()
        return action_f(**execed_inputs)

    usage_results = []
    # outputs will be ordered by the `UsageOutputNames` order, not the
    # signature order - this makes it so that the example writer doesn't
    # need to be explicitly aware of the signature order
    for param_name, var_name in outputs.items():
        # param name is not output-name in archive versions without o.n.
        try:
            qiime_type = action_f.signature.outputs[param_name].qiime_type
        except KeyError:
            # param_name is often a snake-case qiime2 type, so we can check
            # if the same type still exists in the param spec. If so, use it.
            for (p_name, p_spec) in action_f.signature.outputs.items():
                searchable_type_name = camel_to_snake(str(p_spec.qiime_type))
                if param_name == searchable_type_name:
                    qiime_type = action_f.signature.outputs[p_name].qiime_type
                    break

        if is_visualization_type(qiime_type):
            var_type = 'visualization'
        elif is_semantic_type(qiime_type):
            var_type = 'artifact'
        else:  # pragma: no cover
            raise ValueError('unknown output type: %r' % (qiime_type,))

        def factory(name=param_name):  # pragma: no cover
            results = memoized_action()
            result = getattr(results, name)
            return result

        variable = self._usage_variable(var_name, factory, var_type)
        usage_results.append(variable)

    results = UsageOutputs(outputs.keys(), usage_results)
    cache_info = memoized_action.cache_info
    cache_clear = memoized_action.cache_clear
    # manually graft on cache operations
    object.__setattr__(results, '_cache_info', cache_info)
    object.__setattr__(results, '_cache_reset', cache_clear)
    return results


# NOTE: True monkeypatching happening here. Gross, but the alternative is
# overriding more methods from ReplayCLIUsage and ReplayPythonUsage to point
# to a ReplayUsage subclass
Usage.action = action


class ReplayPythonUsageVariable(ArtifactAPIUsageVariable):
    def to_interface_name(self):
        if self.var_type == 'format':
            return self.name

        parts = {
            'artifact': [self.name],
            'visualization': [self.name, 'viz'],
            'metadata': [self.name, 'md'],
            'column': [self.name],
            # No format here - it shouldn't be possible to make it this far
        }[self.var_type]
        var_name = '_'.join(parts)
        # NOTE: This will no longer guarantee valid python identifiers,
        # because it allows <>. We get more human-readable no-prov node names.
        # Alternately, we could replace < and > with e.g. ___, which is
        # unlikely to occur and is still a valid python identifier
        var_name = re.sub(r'[^a-zA-Z0-9_<>]|^(?=\d)', '_', var_name)
        return self.repr_raw_variable_name(var_name)


class ReplayPythonUsage(ArtifactAPIUsage):
    def _template_outputs(self, action, variables):
        """
        Monkeypatch allowing us to replay an action even when our provenance
        DAG doesn't have a record of all outputs from that action.
        """
        output_vars = []
        action_f = action.get_action()

        # need to coax the outputs into the correct order for unpacking
        for output in action_f.signature.outputs:
            try:
                variable = getattr(variables, output)
                output_vars.append(str(variable.to_interface_name()))
            except AttributeError:
                # if the args to UsageOutputNames skip an output name,
                # can we assume the user doesn't care about that output?
                # These assumptions are OK here, but not in the framework.
                # I'm guessing this could break chaining, so maybe
                # this behavior should warn?
                output_vars.append('_')

        if len(output_vars) == 1:
            output_vars.append('')

        return ', '.join(output_vars).strip()

    def init_metadata(self, name, factory):
        var = super().init_metadata(name, factory)
        self._update_imports(from_='qiime2', import_='Metadata')
        input_fp = var.to_interface_name()
        lines = [
            '# NOTE: You may substitute already-loaded Metadata for the '
            'following,\n# or cast a pandas.DataFrame to Metadata as needed.\n'
            f'{input_fp} = Metadata.load(<your metadata filepath>)',
            '',
        ]
        self._add(lines)
        return var

    def import_from_format(self, name, semantic_type, variable,
                           view_type=None):
        """
        Identical to super.import_from_format, but writes <your data here>
        instead of import_fp
        """
        imported_var = Usage.import_from_format(
            self, name, semantic_type, variable, view_type=view_type)

        interface_name = imported_var.to_interface_name()
        # import_fp = variable.to_interface_name()
        import_fp = "<your data here>"

        lines = [
            '%s = Artifact.import_data(' % (interface_name,),
            self.INDENT + '%r,' % (semantic_type,),
            self.INDENT + '%r,' % (import_fp,),
        ]

        if view_type is not None:  # pragma: no cover
            if type(view_type) is not str:
                # Show users where these formats come from when used in the
                # Python API to make things less "magical".
                import_path = super()._canonical_module(view_type)
                view_type = view_type.__name__
                if import_path is not None:
                    self._update_imports(from_=import_path,
                                         import_=view_type)
                else:
                    # May be in scope already, but something is quite wrong at
                    # this point, so assume the plugin_manager is sufficiently
                    # informed.
                    view_type = repr(view_type)
            else:
                view_type = repr(view_type)

            lines.append(self.INDENT + '%s,' % (view_type,))

        lines.append(')')

        self._update_imports(from_='qiime2', import_='Artifact')
        self._add(lines)

        return imported_var

    def usage_variable(self, name, factory, var_type):
        return ReplayPythonUsageVariable(name, factory, var_type, self)


class ReplayCLIUsage(CLIUsage):
    def _append_action_line(self, signature, param_name, value):
        """
        Monkeypatch allowing us to replay when recorded parameter names
        are not present in the registered function signatures in the active
        QIIME 2 environment
        """
        param_state = signature.get(param_name)
        if param_state is not None:
            for opt, val in self._make_param(value, param_state):
                line = self.INDENT + opt
                if val is not None:
                    line += ' ' + val
                line += ' \\'
                self.recorder.append(line)
        else:  # no matching param name
            line = self.INDENT + (
                "# TODO: The following parameter name was not found in "
                "your current\n  # QIIME 2 environment. This may occur "
                "when the plugin version you have\n  # installed does not "
                "match the version used in the original analysis.\n  # "
                "Please see the docs and correct the parameter name "
                "before running.\n")
            cli_name = re.sub('_', '-', param_name)
            line += self.INDENT + '--?-' + cli_name + ' ' + str(value)
            line += ' \\'
            self.recorder.append(line)

    def import_from_format(self, name, semantic_type, variable,
                           view_type=None):
        """
        Identical to super.import_from_format, but writes --input-path <your
        data here>
        """
        # We need the super().super() here, so pass self to Usage.import_fr...
        imported_var = Usage.import_from_format(
            self, name, semantic_type, variable, view_type=view_type)

        # in_fp = variable.to_interface_name()
        out_fp = imported_var.to_interface_name()

        lines = [
            'qiime tools import \\',
            self.INDENT + '--type %r \\' % (semantic_type,)
        ]

        if view_type is not None:  # pragma: no cover
            lines.append(
                self.INDENT + '--input-format %s \\' % (view_type,))

        lines += [
            self.INDENT + '--input-path <your data here> \\',
            self.INDENT + '--output-path %s' % (out_fp,),
        ]

        self.recorder.extend(lines)

        return imported_var


DRIVER_CHOICES = Literal['python3', 'cli']
SUPPORTED_USAGE_DRIVERS = {
    'python3': ReplayPythonUsage,
    'cli': ReplayCLIUsage,
}
DRIVER_NAMES = list(SUPPORTED_USAGE_DRIVERS.keys())
