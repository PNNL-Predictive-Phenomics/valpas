"""
Module containing functions for the calculation of associations used by 
ValPAS.
"""

from copy import deepcopy
from io import TextIOBase
from os import PathLike
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd


from .omics import Omic


class AssociationResult():

    def __init__(
            self,
            values: pd.DataFrame,
            counts: pd.DataFrame,
            omic_x: Omic,
            omic_y: Omic,
            ) -> None:
        
        self.values = values
        self.counts = counts
        self.omic_x = omic_x
        self.omic_y = omic_y
    
    # ---------------------------
    # getters, setters & deleters
    # ---------------------------   

    # values
    @property
    def values(self):
        return self._values
    
    @values.setter
    def values(self, value):
        self._values = value
    
    @values.deleter
    def values(self):
        del self._values

    # counts
    @property
    def counts(self):
        return self._counts
    
    @counts.setter
    def counts(self, value):
        self._counts = value
    
    @counts.deleter
    def counts(self):
        del self._counts

    # omic_x
    @property
    def omic_x(self):
        return self._omic_x
    
    @omic_x.setter
    def omic_x(self, value):
        self._omic_x = value
    
    @omic_x.deleter
    def omic_x(self):
        del self._omic_x

    # omic_y
    @property
    def omic_y(self):
        return self._omic_y    
    
    @omic_y.setter
    def omic_y(self, value):
        self._omic_y = value
    
    @omic_y.deleter
    def omic_y(self):
        del self._omic_y    


    def save(
            self,
            file_handle: str | PathLike | Path | TextIOBase,
            type: Literal['sorted_list', 'assocation_matrix']='sorted_list',
            overwrite: bool=False,
            **kwargs
            ) -> None:
        from ...io import write_outfile

        assocation_metric = kwargs.get('association_metric', 'association')

        if self.omic_y is None:
            self.omic_y = deepcopy(self.omic_x)
            self.omic_x.type = "_".join([self.omic_x.type, "1"])
            self.omic_y.type = "_".join([self.omic_y.type, "2"])

        self.values = _rm_duplicates(
            df=self.values,
            idx1=self.omic_x.features,
            idx2=self.omic_y.features,
        )

        self.counts = _rm_duplicates(
            df=self.counts,
            idx1=self.omic_x.features,
            idx2=self.omic_y.features,
        )

        self.values.index.name = self.omic_x.type
        self.values.columns.name = self.omic_y.type
        
        self.counts.index.name = self.omic_x.type
        self.counts.columns.name = self.omic_y.type
        
        write_outfile(
            data=(self.values, self.counts),
            file_handle=file_handle,
            idx=(self.omic_x.type, self.omic_y.type),
            output_type=type,
            overwrite=overwrite,
            association_type=assocation_metric
        )


def _rm_duplicates(
        df: pd.DataFrame, idx1: pd.Index, idx2: pd.Index=None
        ) -> pd.DataFrame:
    """
    Removes duplicates of omics data pairs that have been generated 
    during the calculation of association values.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame that should be cleaned.
    idx1 : pandas.Index
        Index object containing omics identifiers. If ``idx2`` is not 
        passed to the function the assumption is that items recoreded in
        ``idx1`` are associated with each other.
    idx2 : pandas.Index, default=None
        Index object containing omics identifiers. If provided the
        assumption is that association pairs should only be of type
        [idx1, idx2]. Any pairs [idx1, idx1] or [idx2, idx2] are 
        removed. 

    Returns
    -------
    pandas.DataFrame
        Filtered panadas.DataFrame object that has duplicates removed.

    Notes
    -----
    The function serves two purposes:

    1. If the `DataFrame` passed to the function contains items from 
       only one omics type (indicated by omitting `idx2` / setting it to 
       `None`, see also ``valpas.utils.data_handling.prep_data`)), then
       the function will extract the upper triangle (any association 
       measure implemented should be symmetric i.e. 
       :math:`A(a,b)=A(b,a)`)
    2. If both `idx1` and `idx2` is passed to the function, it is 
       assumed that the DF contains items from two different omics
       types. In this case the DF is filtered such that `DF.index` only 
       contains items from `idx1` and `DF.columns` contains only items
       of `idx2`.
    """

    if idx1.equals(idx2):
        # use case for this block: if the correlation matrix is NxN and 
        # each n in N is from only one data source we can reduce the 
        # output to pervent *association(i,j)* and *association(j,i)*
        # to show up in the output. Note that if the correlation matrix 
        # contains NxM elements and N & M are two different sets of 
        # data points, choosing to reduce the input will remove unique 
        # results.
        # 
        # The code block extracts the upper triangle of the matrix, 
        # sets the lower triangle (including the diagonal) to NaN.
        # `pd.DataFrame.stack()` drops NaNs by default and therefore 
        # excludes the pairs from sorting and being returned.
        upper_tri = np.triu(df, -1)
        upper_tri[np.tril_indices(upper_tri.shape[0], 0)] = np.nan

        df_ret = pd.DataFrame(
            data=upper_tri,
            index=df.index,
            columns=df.columns
            )
        return df_ret
    else:
        # This covers case (2) listed in the docstring, i.e. the 
        # the DataFrame contains data from two different omics data 
        # data types. In this case we filter the DF such that the rows 
        # are limited to items from `idx1` and the columns are limited 
        # to `idx2`.

        df_ret = df.drop(
            labels=df.index.difference(idx2),
            axis='index',
            )
        df_ret.drop(
            labels=df.columns.difference(idx1),
            axis='columns',
            inplace=True)
        return df_ret
