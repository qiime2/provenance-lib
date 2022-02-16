import re
from typing import Literal

from q2cli.core.usage import CLIUsage
from qiime2.plugins import ArtifactAPIUsage, ArtifactAPIUsageVariable
from qiime2.sdk.usage import Usage


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

        if view_type is not None:
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

        if view_type is not None:
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
