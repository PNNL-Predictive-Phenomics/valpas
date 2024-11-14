"""
_summary_

"""
from __future__ import annotations

import pandas as pd


class Experiment():

    def __init__(
            self,
            name: str=None,
            ) -> None:
        
        self.name = name
    
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @name.deleter
    def name(self):
        del self._name    

class SingleExperiment(Experiment):
    """
    Custom Class that stores experiment data.

    Attributes
    ----------
    name: str
        The name for the experiment
    omic_x_values: pandas.DataFrame
        DataFrame containing the raw values extracted from an omic type
        of the experimental setup
    omic_x_type: str
        Name of the omics type that has been evaluated in the experiment
    omic_x_features: pandas.Index
        Contains all features / items of the omics type x that were 
        extracted
    omic_y_values: pandas.DataFrame
        Optional DataFrame containing the raw values extracted from a 
        second omic type of the experimental setup. If not defined (i.e.
        _None_) the assumption is that the associations among only one
        omics type (`omic_x_type`) are going to be coducted.
    omic_y_type: str, default = None
        Optional name of a second omics type that has been evaluated in
        the experiment. If not defined (i.e. _None_) the assumption is
        that associations among only one omics type (`omic_x_type`)
        are going to be conducted.
    omic_y_features: pandas.Index, default = None
        Optional pandas Index object that contains features of omics 
        type y that have been extracted. If not defined (i.e. _None_)
        the assumption is that associations among only one omics type 
        (`omic_x_type`) are going to be conducted. See also 
        `omic_y_type`.

    Methods
    -------
    has_two_omics(self)
        Checks if two omics are present, i.e. if `omic_y_type` is 
        defined.
    """
    def __init__(
            self,
            name: str,
            omic_x_values: pd.DataFrame,
            omic_x_type: str,
            omic_x_features: pd.Index,
            omic_y_values: pd.DataFrame=None,
            omic_y_type: str=None,
            omic_y_features: pd.Index=None,
            ) -> None:
        
        super().__init__(name)

        self.omic_x_values = omic_x_values
        self.omic_x_type = omic_x_type
        self.omic_x_features = omic_x_features
        self.omic_y_values = omic_y_values
        self.omic_y_type = omic_y_type
        self.omic_y_features = omic_y_features
        self.combined_values = None


    def has_two_omics(self) -> bool: 
        """
        _summary_

        Returns
        -------
        bool
            _description_
        """
        if self.omic_y_type is not None:
            return True
        
    
    def combine_omics(self, inplace: bool=False) -> None | SingleExperiment:
    
        from copy import deepcopy

        if inplace:
            experiment_ = self
        else:
            experiment_ = deepcopy(self)

        if experiment_.has_two_omics():
            df = pd.concat(
                [
                    experiment_.omic_x_values,
                    experiment_.omic_y_values
                ],
                join='inner'
                )
        else:
            df = experiment_.omic_x_values
        
        experiment_.combined_values = df

        if inplace:
            return None
        else:
            return experiment_


    def rm_low_confidence_features(
            self,
            threshold: float=0,
            inplace: bool=False
            ) -> None | SingleExperiment:

        from copy import deepcopy
        from .processing import _remove_low_confidence_features

        if inplace:
            experiment_ = self
        else:
            experiment_ = deepcopy(self)

        idx_omic_x = experiment_.omic_x_features
        idx_omic_y = experiment_.omic_y_features

        if experiment_.combined_values is not None:
            df = experiment_.combined_values
        else:
            df = experiment_.omic_x_values

        df, index = _remove_low_confidence_features(df=df, threshold=threshold)
        if len(index.values) > 0:
            # print("Removed items: ", end="", file=sys.stderr)
            # print(*index.values, sep=", ", file=sys.stderr)
            experiment_.combined_values = df
            idx_omic_x_ret = idx_omic_x.difference(index)
            idx_omic_x_ret.name = idx_omic_x.name
            experiment_.omic_x_features = idx_omic_x_ret
            if idx_omic_y is not None:
                idx_omic_y_ret = idx_omic_y.difference(index)
                idx_omic_y_ret.name = idx_omic_y.name
                experiment_.omic_y_features = idx_omic_y_ret
        
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
        from copy import deepcopy
        from .processing import _bin
        from .processing import _threshold_df

        if inplace:
            experiment_ = self
        else:
            experiment_ = deepcopy(self)

        experiment_.combine_omics(inplace=True)
        experiment_.rm_low_confidence_features(
            threshold=rm_low_conf_features,
            inplace=True,
            )

        experiment_vals = experiment_.combined_values

        if bin:
            experiment_vals = _bin(df=experiment_vals)
        
        if threshold:
            experiment_vals = _threshold_df(
                df=experiment_vals,
                threshold_rel=threshold,
                )
        
        # if normalize:
        #     experiment_vals.normalize()

        experiment_.combined_values = experiment_vals.T

        if inplace:
            return None
        else:
            return experiment_

