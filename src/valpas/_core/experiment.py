"""
_summary_

"""

import pandas as pd

class Experiment:
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
            ):
        self.name = name
        self.omic_x_values = omic_x_values
        self.omic_x_type = omic_x_type
        self.omic_x_features = omic_x_features
        self.omic_y_values = omic_y_values
        self.omic_y_type = omic_y_type
        self.omic_y_features = omic_y_features

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
