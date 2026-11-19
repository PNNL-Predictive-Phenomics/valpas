"""Opt-in production sidecars and unchanged legacy defaults."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_a1_contracts import descriptor
from test_a1_export import Matrix
from valpas.comparison import (ComparisonValidationError, export_association_result,
                               load_export_request, load_input_bundle)
from valpas.comparison.production import export_requested_result


class ProductionTests(unittest.TestCase):
    def result(self):
        return SimpleNamespace(values=Matrix(['q'], ['a', 'b', 'c'], [[-.9123456789123456, .8, None]]), counts=None)

    def test_detached_precision_unknowns_and_extra_metadata(self):
        d = descriptor()
        d['seed'] = None
        d['configuration']['parameters']['custom'] = {'unknown': None}
        d['configuration']['preprocessing'] = None
        original = copy.deepcopy(d)
        result = self.result()
        with tempfile.TemporaryDirectory() as tmp:
            dest = export_association_result(result, Path(tmp) / 'input', d, query_axis='index')
            output = load_input_bundle(dest).outputs[0]
            self.assertEqual(output.pair('q', 'a').score, -.9123456789123456)
            self.assertIsNone(output.descriptor['seed'])
            self.assertIsNone(output.descriptor['configuration']['preprocessing'])
            self.assertIsNone(output.descriptor['configuration']['parameters']['custom']['unknown'])
            self.assertEqual(d, original)
            result.values.cells['q', 'a'] = 8
            self.assertEqual(output.pair('q', 'a').score, -.9123456789123456)

    def test_similarity_result_without_training(self):
        result = SimpleNamespace(similarity_matrix=self.result().values)
        with tempfile.TemporaryDirectory() as tmp:
            dest = export_association_result(result, Path(tmp) / 'input', descriptor(), query_axis='index')
            self.assertIsNone(load_input_bundle(dest).outputs[0].pair('q', 'a').count)

    def test_capture_fills_unknown_and_rejects_conflicts(self):
        d = descriptor()
        d['identity']['observation_ids'] = None
        d['configuration']['parameters'] = None
        d['configuration']['supervision'] = None
        with tempfile.TemporaryDirectory() as tmp:
            dest = export_association_result(self.result(), Path(tmp) / 'input', d, query_axis='index',
                                            observation_ids=[' 01', '02'], method='pearson', transform_clr=False)
            out = load_input_bundle(dest).outputs[0]
            self.assertEqual(tuple(out.descriptor['identity']['observation_ids']), (' 01', '02'))
            self.assertEqual(out.descriptor['configuration']['parameters']['valpas_method'], 'pearson')
            self.assertIsNone(d['identity']['observation_ids'])
            for changes in ({'observation_ids': ['other']}, {'method': 'spearman'}):
                with self.assertRaises(ComparisonValidationError):
                    export_association_result(self.result(), Path(tmp) / 'bad', out.descriptor,
                                              query_axis='index', **changes)
                self.assertFalse((Path(tmp) / 'bad').exists())

    def test_request_strict_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = {'descriptor': descriptor(), 'query_axis': 'index', 'destination': str(Path(tmp) / 'input')}
            path = Path(tmp) / 'request.json'
            path.write_text(json.dumps(request))
            self.assertEqual(load_export_request(path), request)
            export_requested_result(self.result(), path)
            with self.assertRaises(ComparisonValidationError):
                export_requested_result(self.result(), request)
            for key, value in [('extra', 1), ('query_axis', 'guess')]:
                with self.assertRaises(ComparisonValidationError):
                    load_export_request(dict(request, **{key: value}))
            path.write_text('{"descriptor": 1, "descriptor": 2}')
            with self.assertRaises(ComparisonValidationError):
                load_export_request(path)

    def test_result_method_does_not_call_legacy_save(self):
        import pandas as pd
        from valpas import AssociationResult
        result = AssociationResult(pd.DataFrame([[-.9, .8, .1]], index=['q'], columns=['a', 'b', 'c']), None, None, None)
        before = result.values.copy(deep=True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(result, 'save', side_effect=AssertionError), patch.object(result, 'as_list', side_effect=AssertionError):
            result.export_comparison(Path(tmp) / 'input', descriptor(), query_axis='index')
        pd.testing.assert_frame_equal(result.values, before)
        self.assertIsNone(result.omic_y)

    def test_calculation_capture_after_subset_and_default_no_export(self):
        import pandas as pd
        from valpas._core.association import calculate_association
        data = pd.DataFrame({'q': [1., 2., 3., 4.], 'a': [4., 2., 3., 1.],
                             'b': [2., 4., 1., 3.], 'c': [1., 4., 2., 3.]}, index=['s1', 's2', 's3', 's4'])
        subset = SimpleNamespace(measurements=data.iloc[:3], omic_x=None, omic_y=None)
        experiment = SimpleNamespace(measurements=data, omic_x=None, omic_y=None,
                                     subset_by_conditions=Mock(return_value=subset))
        d = descriptor()
        d['identity']['observation_ids'] = None
        d['count_semantics'] = 'Legacy pandas corr callable counts; diagonal is pandas unity, not an observed count'
        d['configuration']['supervision'] = None
        with tempfile.TemporaryDirectory() as tmp:
            request = {'descriptor': d, 'query_axis': 'index', 'destination': str(Path(tmp) / 'input')}
            with patch('valpas._core.association.StatisticalAssociationResults', return_value=object()):
                ordinary = calculate_association(subset, subset_args={'nconds': None, 'percentage': None, 'keep_conds': []})
                self.assertFalse((Path(tmp) / 'input').exists())
                captured = calculate_association(experiment, subset_args={'nconds': 3, 'percentage': None, 'keep_conds': []}, comparison_export=request)
            experiment.subset_by_conditions.assert_called_once()
            pd.testing.assert_frame_equal(ordinary.values, captured.values)
            self.assertEqual(tuple(load_input_bundle(Path(tmp) / 'input').outputs[0].descriptor['identity']['observation_ids']), tuple(subset.measurements.index))

    def test_experiment_default_does_not_add_keyword(self):
        from valpas._core.classes.experiments import Experiment
        with patch('valpas._core.classes.experiments.calculate_association') as calculate:
            Experiment.associate(object())
            self.assertNotIn('comparison_export', calculate.call_args.kwargs)
            Experiment.associate(object(), comparison_export={'explicit': True})
            self.assertEqual(calculate.call_args.kwargs['comparison_export'], {'explicit': True})


class DispatchTests(unittest.TestCase):
    result = ProductionTests.result

    def test_cli_exports_before_mutating_save_and_survives_legacy_failure(self):
        from valpas import cli
        for fail_save in (False, True):
            with self.subTest(fail_save=fail_save), tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp) / 'input'
                d = descriptor()
                d['identity']['observation_ids'] = None
                d['configuration']['supervision'] = None
                result = self.result()
                def save(**kwargs):
                    self.assertTrue(destination.is_dir())
                    result.values.cells['q', 'a'] = 0
                    if fail_save:
                        raise OSError('legacy publication failed')
                result.save = Mock(side_effect=save)
                experiment = Mock()
                experiment.measurements.index = ['actual 01', 'actual 02']
                experiment.associate.return_value = result
                args = SimpleNamespace(comparison_export={
                    'descriptor': d, 'query_axis': 'index', 'destination': str(destination)},
                    csv=True, xlsx=False, SHEET=None, SHEET2=None,
                    SOURCE='from_file', INFILE='source.csv', INFILE2=None,
                    ASSOCIATION_TYPE='pearson', FILTER_CUTOFF=.9, NORMALIZATION='none',
                    OUTFILE='legacy.csv', OUTPUT_TYPE='correlation_matrix', OVERWRITE_OUTPUT=False)
                with patch('valpas.io.import_experiments', return_value=[experiment]):
                    if fail_save:
                        with self.assertRaises(OSError):
                            cli.associate(args)
                    else:
                        cli.associate(args)
                out = load_input_bundle(destination).outputs[0]
                self.assertEqual(out.pair('q', 'a').score, -.9123456789123456)
                self.assertEqual(tuple(out.descriptor['identity']['observation_ids']), ('actual 01', 'actual 02'))
                result.save.assert_called_once_with(file_handle='legacy.csv', type='correlation_matrix',
                                                    overwrite=False, assocation_metric='pearson')

    def test_destination_collision_rejected_before_calculation(self):
        from valpas import cli, valpas_core
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'input'
            request = {'descriptor': descriptor(), 'query_axis': 'index', 'destination': str(destination)}
            legacy = destination / 'legacy.csv'
            with patch('valpas.io.import_experiments') as importer:
                with self.assertRaises(ComparisonValidationError):
                    cli.associate(SimpleNamespace(comparison_export=request, OUTFILE=legacy))
                importer.assert_not_called()
            with patch.object(valpas_core, 'import_experiments') as importer:
                with self.assertRaises(ComparisonValidationError):
                    valpas_core.associate(comparison_export=request, outfile=legacy)
                importer.assert_not_called()
            self.assertFalse(destination.exists())

    def test_high_level_exports_before_as_list_and_save(self):
        from valpas import valpas_core
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'input'
            result = self.result()
            def mutate(**kwargs):
                self.assertTrue(destination.is_dir())
                result.values.cells['q', 'a'] = 0
                return 'legacy edges'
            result.as_list = Mock(side_effect=mutate)
            result.save = Mock()
            experiment = Mock()
            experiment.associate.return_value = result
            d = descriptor()
            d['configuration']['supervision'] = None
            with patch.object(valpas_core, 'import_experiments', return_value=[experiment]):
                returned = valpas_core.associate(infile='source.csv', comparison_export={
                    'descriptor': d, 'query_axis': 'index', 'destination': str(destination)})
            self.assertIs(returned, result)
            self.assertEqual(load_input_bundle(destination).outputs[0].pair('q', 'a').score, -.9123456789123456)
            result.as_list.assert_called_once_with(min_counts=3)
            result.save.assert_called_once()


if __name__ == '__main__':
    unittest.main()
