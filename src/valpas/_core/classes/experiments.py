"""
_summary_

"""
from __future__ import annotations

from copy import deepcopy
from typing import Literal
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from ..association import calculate_association
from ..processing import normalize as normalize_
from .omics import Omic

if TYPE_CHECKING:
    from valpas._typing import(
        AssociationResult,
        OmicMeasurement,
    )


class Experiment():
    """
    Parent Class for ``SingleExperiment`` and ``CrossExperiment``.

    Parameters
    ----------
    name : str
        Name of the experiment.
    measurements : pandas.DataFrame
        pandas DataFrame that contains the measurements associated with
        the experiment.

    """

    def __init__(
            self,
            name: str=None,
            measurements: pd.DataFrame=None,
            ) -> None:

        self.name = name
        self.measurements = measurements


    # ---------------------------
    # getters, setters & deleters
    # ---------------------------

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @name.deleter
    def name(self):
        del self._name

    @property
    def measurements(self):
        return self._measurements

    @measurements.setter
    def measurements(self, value):
        self._measurements = value

    @measurements.deleter
    def measurements(self):
        del self._measurements


    # ------------------
    # instance functions
    # ------------------

    def associate(
            self,
            metric: Literal[
                'pearson', 'spearman',
                'jaccard_similarity', 'jaccard_distance', 'jaccard_index',
                'mutual_information',
                'cosine_similarity', 'cosine_distance',
                ]='pearson',
            thresholded: bool=False,
            training_interactions: list=None,
            transform_clr: bool=False,
            learncorr_args: dict={},
            autoencoder_args: dict={},
            subset_args: dict={}
            ) -> AssociationResult:
        """
        Function that calculates association values for the Experiment.

        Parameters
        ----------
        metric : {'pearson', 'spearman', 'jaccard_similarity',\
                  'jaccard_distance', 'jaccard_index',\
                  'mutual_information', 'cosine_similarity',\
                  'cosine_distance'\
                  }, default='pearson'
            Association metric that should be used for the association
            calculation.

        thresholded : bool, default=False
            Defines if the association metric requires a thresholded
            `measurements` table.
        learncorr_args: dict={}
             Keyword args for learn correlation
        autoencoder_args: dict={}
            Keyword args for autoencoder
        subset_args: dict={}
            Keyword args for subsetting

        Returns
        -------
        AssociationResult
            Returns an AssociationResult object that contains the
            association values as well as counts for how many features
            contributed to the association calculation.
        """

        return calculate_association(
            self,
            method=metric,
            thresholded=thresholded,
            training_interactions=training_interactions,
            transform_clr=transform_clr,
            learncorr_args=learncorr_args,
            autoencoder_args=autoencoder_args,
            subset_args=subset_args
            )

class SingleExperiment(Experiment):
    """
    Object that stores information related to a single experiment.
    Contains up to two ``OmicMeasurement`` objects storing the omic
    measurement information.

    Attributes
    ----------
    name: str
        The name for the experiment
    omic_x : OmicMeasurement
        Object containing the measurement data for a single omic type as
        well as associated metadata. See also ``valpas.OmicMeasurement``.
    omic_y : OmicMeasurement
        See `omic_x`. Only used if associations are generated between
        two different omic types.

    Methods
    -------
    has_two_omics(self)
        Checks if two omics are present, i.e. if `omic_y_type` is
        defined.
    """
    def __init__(
            self,
            name: str,
            omic_x: OmicMeasurement,
            omic_y: OmicMeasurement=None,
            ) -> None:

        super().__init__(name)

        self.omic_x = omic_x
        self.omic_y = omic_y


    # ---------------------------
    # getters, setters & deleters
    # ---------------------------

    @property
    def omic_x(self):
        return self._omic_x

    @omic_x.setter
    def omic_x(self, value):
        self._omic_x = value

    @omic_x.deleter
    def omic_x(self):
        del self._omic_x

    @property
    def omic_y(self):
        return self._omic_y

    @omic_y.setter
    def omic_y(self, value):
        self._omic_y = value

    @omic_y.deleter
    def omic_y(self):
        del self._omic_y


    # ------------------
    # instance functions
    # ------------------


    def combine_omics(self, inplace: bool=False) -> None | SingleExperiment:
        """
        Helper function that combines measurements from two omic types
        into one pandas.DataFrame stored in the `measurements` attribute
        of the object.

        Parameters
        ----------
        inplace : bool, default=False
            If set to `True` combines the two omics measurements and
            stores the resulting DataFrame in the `measurements`
            attribute of the class instance.

        Returns
        -------
        None | SingleExperiment
            Returns `None` if `inplace==True`. Otherwise a new
            `SingleExperiment` instance containing the combined
            measurments is returned.
        """

        if inplace:
            experiment_ = self
        else:
            experiment_ = deepcopy(self)

        if experiment_.has_two_omics():
            df = pd.concat(
                [
                    experiment_.omic_x.measurements,
                    experiment_.omic_y.measurements,
                ],
                join='inner'
                )
        else:
            df = experiment_.omic_x.measurements

        experiment_.measurements = df

        if inplace:
            return None
        else:
            return experiment_

    def has_two_omics(self) -> bool:
        """
        Helper function to checks the experiment uses two different
        omic types.

        Returns
        -------
        bool
            True if two Omic classes are present in the Experiment
        """
        if self.omic_y is not None:
            return True


    def normalize(
            self,
            method: Literal['z-score', 'pareto', 'power-scaling']='z-score',
            inplace: bool=False,
            ) -> None | SingleExperiment:
        """
        Normalizes omics measurements. Designed to be used in
        conjunction with CrossExperiments, where individual
        SingleExperiments omics measurements are normalized before they
        are combined into a CrossExperiment.

        Parameters
        ----------
        method : {'z-score', 'pareto', 'power-scaling'}, \
            default='z-score'
            Defines the normalization method to be used.
        inplace : bool, default=False
            If set to `True` the method will normalize the values
            inplace and return `None`, otherwise a copy of the
            `SingleExperiment` will be returned.

        Returns
        -------
        None | SingleExperiment
            Returns either `None` or a copy of the `SingleExperiment`
            depending on the value of `inplace`.
        """

        if inplace:
            experiment_ = self
        else:
            experiment_ = deepcopy(self)

        experiment_.omic_x.measurements = normalize_(
            data=experiment_.omic_x.measurements,
            method=method
        )

        if experiment_.has_two_omics():
            experiment_.omic_y.measurements = normalize_(
                data=experiment_.omic_y.measurements,
                method=method
            )

        if inplace:
            return None
        else:
            return experiment_


    def pre_process(
            self,
            normalize: bool=False,
            rm_low_conf_features: float=0,
            threshold: float=None,
            bin: bool=False,
            inplace: bool=False,
            ) -> None | SingleExperiment:
        """
        Pre processing function for experiment data.

        Parameters
        ----------
        normalize : bool, default=False
            If set to `True`, executes ``normalize()`` function before
            combining the OmicMeasurement data (if two OmicMeasurements
            are defined). See also ``normalize()``
        rm_low_conf_features : float, default=None
            Defines the fraction of datapoints per features that need to
            present such that a feature is considered confident and kept
            in the dataset. See also ``rm_low_confidence_features``.
        threshold : float, default=None
            Defines if the OmicsMeasurements need to thresholded
            (required for calculation of JaccardIndex for example) and
            the relative threshold (e.g. 0.5 would be the midpoint
            between the largest and smallest value recorded for a
            feature).
        bin : bool, default=False
            (Deprecated) Defines if the OmicsMeasurements need to be
            binned.
        inplace : bool, default=False
            If set to `True` the pre processing will be done on the
            object itself and `None` is returned. Otherwise a copy of
            the object is returned.

        Returns
        -------
        None | SingleExperiment
            Returns `None` if ``inplace==True`` otherwise returns a copy
            of the object.
        """

        from ..processing import _bin
        from ..processing import _threshold_df

        if inplace:
            experiment_ = self
        else:
            experiment_ = deepcopy(self)

        # Temporary solution to setting 0 as nan until we figure out the
        # order of operations for pre_process
        #
        # TODO: figure out if we want to keep this here or move
        experiment_.omic_x.measurements.replace(0, np.nan, inplace=True)
        if experiment_.omic_y is not None:
            experiment_.omic_y.measurements.replace(0, np.nan, inplace=True)

        if normalize:
            experiment_.normalize(inplace=True)

        experiment_.combine_omics(inplace=True)
        experiment_.rm_low_confidence_features(
            threshold=rm_low_conf_features,
            inplace=True,
            )

        experiment_vals = experiment_.measurements

        if bin:
            experiment_vals = _bin(df=experiment_vals)

        if threshold:
            experiment_vals = _threshold_df(
                df=experiment_vals,
                threshold_rel=threshold,
                )

        experiment_.measurements = experiment_vals.T

        if inplace:
            return None
        else:
            return experiment_


    def rm_low_confidence_features(
            self,
            threshold: float=0,
            inplace: bool=False
            ) -> None | SingleExperiment:
        """
        Removes features (e.g. metabolites) that don't have enough
        measurements to be used reliably in the association calculation.

        Parameters
        ----------
        threshold : float, default=0
            Threshold that has to be satisfied for features to be deemed
            confident. Fraction of conditions for which measurements
            were able to be extracted needs to be larger than
            `threshold`.
        inplace : bool, default=False
            If set to `True` the removal of low confidence values will
            happen inplace, i.e. the underlying DataFrame will be
            modified.

        Returns
        -------
        None | SingleExperiment
            Returns `None` if `inplace==True`. Otherwise a new
            `SingleExperiment` instance containing the measurments
            without the low confidence features is returned.
        """

        # default behaviour of the function is to work on a deepcopy of
        # the Experiment object
        if inplace:
            experiment_ = self
        else:
            experiment_ = deepcopy(self)

        # retrieving the indices of the features
        idx_omic_x = experiment_.omic_x.features
        if experiment_.has_two_omics():
            idx_omic_y = experiment_.omic_y.features
        else:
            idx_omic_y = None

        if experiment_.measurements is not None:
            df = experiment_.measurements
        else:
            df = experiment_.omic_x.measurements

        # treating '0' as NaNs for easier counting of missing values
        df.replace(0, np.nan, inplace=True)

        # creating an index of rows (items) to filter i.e. finding the rows
        # that where the fraction of NAs is larger than 1-cutoff
        s = (
            (df.isna() # create truth table whether values is NaN
            .sum(axis=1) # sum "True" iterating over columns for each row
            /df.shape[1]) # divide by the number of columns
            .gt(1-threshold) # check if fraction of NAs (in row) is > cutoff
            )
        index = s[s].index # creating the actual index (i.e. which rows to drop)

        # filter the DataFrame
        df = df.drop(
            labels=index, # using the defined index from above
            axis='index', # drop based on rows
            )

        # if the above procedure generated columns (conditions) that contain
        # only NAs as values, those will be removed.
        df.dropna(axis="columns", how="all", inplace=True)

        if len(index.values) > 0:
            experiment_.measurements = df
            idx_omic_x_ret = idx_omic_x.difference(index)
            idx_omic_x_ret.name = idx_omic_x.name
            experiment_.omic_x.features = idx_omic_x_ret
            if idx_omic_y is not None:
                idx_omic_y_ret = idx_omic_y.difference(index)
                idx_omic_y_ret.name = idx_omic_y.name
                experiment_.omic_y.features = idx_omic_y_ret

        if inplace:
            return None
        else:
            return experiment_


    def subset_by_conditions(
                self,
                nconds: int=None,
                percentage: float=0.5,
                keep_conds: list=[],
                inplace: bool=False,
                random_state: int=0,
                **kwargs
                ) -> SingleExperiment:
        """
        Returns a copy of the experiment with a subset of conditions retained.

        Parameters
        ----------
        nconds : int, default=None
            Number of (random) conditions to retain.
        percentage : float, default=0.5
            Percentage of (random) conditions to retain.
        keep_conds :  list, default=[]
            A list of condition names to retain.
        inplace : bool, default=False
            If set to `True` the subsetting will be done
            with self, otherwise will return a copy.
        random_state : int, default=0
            Pass in a random seed to set if non-zero.

        Returns
        -------
        None | SingleExperiment
            Returns `None` if `inplace==True`. Otherwise returns a new
            `SingleExperiment` instance containing the measurements
            with a subset of the columns retained.
        """

        # default behaviour of the function is to work on a deepcopy of
        # the Experiment object
        if inplace:
            experiment_ = self
        else:
            experiment_ = deepcopy(self)

        if experiment_.measurements is not None:
            df = experiment_.measurements
        else:
            df = experiment_.omic_x.measurements

        if random_state:
            np.random.seed(random_state)

        if percentage:
            nconds = int(len(df.index) * percentage)

        if keep_conds:
            df = df[[cond for cond in keep_conds if cond in df.index]]

        elif nconds:
            # we want to keep nconds and drop the rest
            dconds = len(df.index) - nconds
            conds_to_drop = np.random.choice(df.index, size=min(dconds, len(df.index)), replace=False)
            df = df.drop(index=conds_to_drop)

        if experiment_.measurements is not None:
            experiment_.measurements = df
        else:
            experiment_.omic_x.measurements = df

        if inplace:
            return None
        else:
            return experiment_


class CrossExperiment(Experiment):
    """
    Object that contains information and data regarding cross experiment
    association analysis.

    Attributes
    ----------
    name: str
        The name for the experiment
    experiments : list[SingleExperiment]
        List containing ``SingleExperiment`` objects to be investigated
        in the Cross Experiment analysis
    omic_x : Omic
        Object containing metadatafor a single omic type. See also
        ``valpas.Omic``.
    omic_y : Omic
        See `omic_x`. Only used if associations are generated between
        two different omic types.
    """

    def __init__(
            self,
            name: str,
            experiments: list[SingleExperiment],
            omic_x: Omic=None,
            omic_y: Omic=None,
            ) -> None:

        super().__init__(name)

        self.experiments = experiments
        self.omic_x = omic_x
        self.omic_y = omic_y


    # ---------------------------
    # getters, setters & deleters
    # ---------------------------

    @property
    def experiments(self):
        return self._experiments

    @experiments.setter
    def experiments(self, value):
        self._experiments = value

    @experiments.deleter
    def experiments(self):
        del self._experiments

    @property
    def omic_x(self):
        return self._omic_x

    @omic_x.setter
    def omic_x(self, value):
        self._omic_x = value

    @omic_x.deleter
    def omic_x(self):
        del self._omic_x

    @property
    def omic_y(self):
        return self._omic_y

    @omic_y.setter
    def omic_y(self, value):
        self._omic_y = value

    @omic_y.deleter
    def omic_y(self):
        del self._omic_y

    # ------------------
    # instance functions
    # ------------------


    def combine(
            self,
            axis: Literal['omics', 'conditions']='omics',
            inplace: bool=False,
            ) -> None | CrossExperiment:
        """
        Helper function that combines individual SingleExperiments
        measurements associated with the CrossExperiment object into one
        measurement attribute.

        Parameters
        ----------
        axis : {'omics', 'conditions'}, default='omics'
            Defines whether omics or conditions should be used as keys
            to combine the measurement tables.
        inplace : bool, default=False
            If set to `True` performs the process of combining inplace
            and returns `None`. Otherwise combining is done on a copy of
            the object and the copy is returned.

        Returns
        -------
        None | CrossExperiment
            Returns `None` if ``inplace==True``, otherwise returns a
            copy of the object.

        Raises
        ------
        ValueError
            If axis contains 'ilegal' value.
        ValueError
            If omics types between the individual SingleExperiments
            don't agree.
        """

        if inplace:
            experiment_ = self
        else:
            experiment_ = deepcopy(self)

        measurments = None
        omic_x_features = None
        omic_x_type = None
        omic_y_features = None
        omic_y_type = None

        if axis == 'omics':
            axis_ = 'index'
        elif axis == 'conditions':
            axis_ = 'columns'
        else:
            raise ValueError(f"'{axis}' not in allowed values for 'axis'.")

        for experiment in experiment_.experiments:
            if measurments is None:
                measurments = experiment.measurements
            else:
                measurments = pd.concat(
                    objs=[
                        measurments,
                        experiment.measurements,
                    ],
                    axis=axis_,
                    join='inner'
                )
            if omic_x_type is None:
                omic_x_type = experiment.omic_x.type
            elif omic_x_type != experiment.omic_x.type:
                raise ValueError(
                    f"Omic types don't match during CrossExperiment combining."
                    f"omics attempted to be combined: '{omic_x_type}' & "
                    f"'{experiment.omic_x.type}'."
                )
            if omic_y_type is None:
                omic_y_type = experiment.omic_y.type
            elif omic_y_type != experiment.omic_y.type:
                raise ValueError(
                    f"Omic types don't match during CrossExperiment combining."
                    f"omics attempted to be combined: '{omic_y_type}' & "
                    f"'{experiment.omic_y.type}'."
                )
            if omic_x_features is None:
                omic_x_features = experiment.omic_x.features
            else:
                omic_x_features = omic_x_features.intersection(
                    experiment.omic_x.features
                    )
            if omic_y_features is None:
                omic_y_features = experiment.omic_y.features
            else:
                omic_y_features = omic_y_features.intersection(
                    experiment.omic_y.features
                    )

        experiment_.omic_x = Omic(omic_x_type, omic_x_features)
        experiment_.omic_y = Omic(omic_y_type, omic_y_features)
        experiment_.measurements = measurments

        if inplace:
            return None
        else:
            return experiment_
