"""A0 regressions, runnable with unittest or pytest; no training is performed."""

from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


SOURCE = Path(__file__).resolve().parents[2] / "src"
EXPORTS = {
    "autoencoder": ("valpas._core.autoencoder", None),
    "confidence_evaluation": ("valpas.confidence_evaluation", None),
    "AnnotationList": ("valpas._core.classes.annotations", "AnnotationList"),
    "AnalysisResults": ("valpas._core.classes.results", "AnalysisResults"),
    "AssociationResult": ("valpas._core.classes.results", "AssociationResult"),
    "Omic": ("valpas._core.classes.omics", "Omic"),
    "OmicMeasurement": ("valpas._core.classes.omics", "OmicMeasurement"),
    "SingleExperiment": ("valpas._core.classes.experiments", "SingleExperiment"),
    "CrossExperiment": ("valpas._core.classes.experiments", "CrossExperiment"),
}

# Blocking attempts (rather than merely checking sys.modules) also detects
# imports hidden behind try/except ImportError in future implementations.
IMPORT_GUARD = '''
import importlib.abc
import sys
import warnings

blocked = (
    "torch", "numpy", "pandas", "scipy", "sklearn", "matplotlib",
    "seaborn", "networkx", "plotly", "bspline_mutual_information",
    "valpas._core", "valpas.confidence_evaluation", "valpas.io",
    "valpas.visualization", "valpas.utils.validator", "valpas.valpas_core",
)
attempts = []
class ImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == p or fullname.startswith(p + ".") for p in blocked):
            attempts.append(fullname)
            raise AssertionError("Forbidden lightweight-path import: " + fullname)

sys.meta_path.insert(0, ImportGuard())
before_filters = list(warnings.filters)
before_showwarning = warnings.showwarning
'''
IMPORT_ASSERTIONS = '''
assert not attempts, attempts
assert warnings.filters == before_filters, (before_filters, warnings.filters)
assert warnings.showwarning is before_showwarning
assert not any(n == p or n.startswith(p + ".") for n in sys.modules for p in blocked)
'''


class SubprocessCase(unittest.TestCase):
    def run_python(self, code):
        # Ignore inherited PYTHONPATH/site customizations and explicitly test the
        # working source tree, from outside the repository. Use its generated
        # version module as-is; never fabricate package/version dependencies.
        bootstrap = f"import sys; sys.path.insert(0, {str(SOURCE)!r})\n"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-I", "-c", bootstrap + textwrap.dedent(code)],
                cwd=directory, capture_output=True, text=True, timeout=60,
            )
        if result.returncode == 77:
            self.skipTest(result.stdout.strip())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result


class TestLightweightImports(SubprocessCase):
    def test_package_and_comparison_imports_preserve_warnings(self):
        for statement in (
            "import valpas",
            "import valpas.comparison",
            "from valpas import comparison",
            "import valpas.cli",
        ):
            with self.subTest(statement=statement):
                self.run_python(IMPORT_GUARD + statement + "\n" + IMPORT_ASSERTIONS)

    def test_all_existing_help_paths_without_scientific_imports(self):
        paths = [
            [], ["--help"], ["associate", "--help"],
            ["associate", "from_file", "--help"],
            ["associate", "from_folder", "--help"],
            ["prepare", "--help"], ["prepare", "from_file", "--help"],
            ["prepare", "from_folder", "--help"], ["visualize", "--help"],
        ]
        for arguments in paths:
            with self.subTest(arguments=arguments):
                code = IMPORT_GUARD + f'''
import runpy
sys.argv = ["valpas", *{arguments!r}]
try:
    runpy.run_module("valpas.cli", run_name="__main__")
except SystemExit as exc:
    assert exc.code == 0, exc.code
else:
    raise AssertionError("Expected help to exit")
''' + IMPORT_ASSERTIONS
                result = self.run_python(code)
                self.assertIn("usage:", result.stdout + result.stderr)

    def test_public_names_discovery_versions_and_unknown_attributes(self):
        self.run_python(IMPORT_GUARD + f'''
import valpas
from valpas._version import __version__, __version_tuple__
assert valpas.__all__ == {list(EXPORTS)!r}
assert set(valpas.__all__).issubset(dir(valpas))
assert not set(valpas.__all__).intersection(vars(valpas))
assert valpas.__version__ == __version__
assert valpas.__version_tuple__ == __version_tuple__
assert not hasattr(valpas, "nonexistent_public_name")
try:
    valpas.nonexistent_public_name
except AttributeError as exc:
    assert "valpas" in str(exc) and "nonexistent_public_name" in str(exc)
else:
    raise AssertionError("Unknown attributes must raise AttributeError")
''' + IMPORT_ASSERTIONS)

    def test_lazy_resolution_caches_each_export(self):
        # Exercise every mapping even in environments missing training extras.
        # Real import identity is tested separately below, never with stubs.
        self.run_python(f'''
from types import SimpleNamespace
from unittest.mock import patch
import valpas
exports = {EXPORTS!r}
for name, (module_name, attribute) in exports.items():
    sentinel = object()
    module = SimpleNamespace(**{{attribute: sentinel}}) if attribute else sentinel
    with patch.object(valpas, "_import_module", return_value=module) as load:
        assert getattr(valpas, name) is sentinel
        assert getattr(valpas, name) is sentinel
        load.assert_called_once_with(module_name.removeprefix("valpas"), "valpas")
''')

    def test_failed_lazy_import_can_be_retried(self):
        self.run_python('''
from unittest.mock import patch
import valpas
with patch.object(valpas, "_import_module", side_effect=ModuleNotFoundError("missing dependency")):
    try:
        valpas.autoencoder
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError("Import failure must propagate")
assert "autoencoder" not in vars(valpas)
sentinel = object()
with patch.object(valpas, "_import_module", return_value=sentinel):
    assert valpas.autoencoder is sentinel
''')


class TestLegacyExports(SubprocessCase):
    """Real legacy imports; absent dependencies are explicit skips, not mocks."""


def legacy_import_test(name, module_name, attribute):
    def test(self):
        # Only known third-party dependency failures may skip. Broken package
        # names and circular-import errors must fail this regression test.
        self.run_python(f'''
import importlib
import sys
known_dependencies = {{"torch", "pandas", "numpy", "scipy", "sklearn", "matplotlib", "seaborn", "networkx", "plotly", "bspline_mutual_information"}}
try:
    import valpas
    namespace = {{}}
    exec("from valpas import {name}", namespace)
    exported = namespace[{name!r}]
    module = importlib.import_module({module_name!r})
    expected = getattr(module, {attribute!r}) if {attribute!r} else module
    assert exported is expected
    assert getattr(valpas, {name!r}) is expected
    assert vars(valpas)[{name!r}] is expected
except ModuleNotFoundError as exc:
    if exc.name.split(".")[0] not in known_dependencies:
        raise
    print("Legacy export {name} blocked by missing dependency: " + exc.name)
    sys.exit(77)
''')
    return test


for _name, (_module, _attribute) in EXPORTS.items():
    setattr(TestLegacyExports, "test_import_" + _name,
            legacy_import_test(_name, _module, _attribute))


class TestLegacyCliDispatch(SubprocessCase):
    def test_handlers_keep_existing_arguments_and_calls(self):
        # Isolated test doubles verify dispatch without running analysis. Heavy
        # modules are installed only after the lightweight CLI is imported.
        self.run_python('''
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
import sys
import valpas
from valpas import cli

io = ModuleType("valpas.io")
processing = ModuleType("valpas._core.processing")
validator = ModuleType("valpas.utils.validator")
heatmap = ModuleType("valpas.visualization.heatmap")
experiment = Mock()
io.import_experiments = Mock(side_effect=lambda **kw: [experiment])
io.import_asssociation_matrix = Mock(return_value="saved-matrix")
processing.combine_results = Mock()
validator.validate_input = Mock()
heatmap.create_fig = Mock()
args = SimpleNamespace(
    csv=True, xlsx=False, SHEET=None, SHEET2=None, SOURCE="from_file",
    INFILE=Path("input.csv"), INFILE2=None, ASSOCIATION_TYPE="pearson",
    FILTER_CUTOFF=0.9, OUTFILE="out.csv", OUTPUT_TYPE="sorted_list",
    OVERWRITE_OUTPUT=False,
)
with patch.dict(sys.modules, {
    "valpas.io": io, "valpas._core.processing": processing,
    "valpas.utils.validator": validator,
    "valpas.visualization.heatmap": heatmap,
}), patch.dict(vars(valpas), {"CrossExperiment": Mock()}):
    cli.associate(args)
    io.import_experiments.assert_called_once_with(
        path=args.INFILE, file_type="csv", source="from_file", path2=None, sheet_names=None)
    experiment.pre_process.assert_called_once_with(
        rm_low_conf_features=0.9, threshold=None, inplace=True)
    experiment.associate.assert_called_once_with(metric="pearson", thresholded=False)
    experiment.associate.return_value.save.assert_called_once_with(
        file_handle="out.csv", type="sorted_list", overwrite=False, assocation_metric="pearson")
    cli.prepare(args)
    validator.validate_input.assert_called_once_with([experiment])
    cli.visualize(SimpleNamespace(TYPE="heatmap", SHEET=None,
        INFILE=Path("scores.csv"), OUTFILE="figure.png", LABEL="Strength"))
    io.import_asssociation_matrix.assert_called_once_with(filepath=Path("scores.csv"), sheet=0)
    heatmap.create_fig.assert_called_once_with(df="saved-matrix", fig_out="figure.png", cbarlabel="Strength")
''')


if __name__ == "__main__":
    unittest.main()
