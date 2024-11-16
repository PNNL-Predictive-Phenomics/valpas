"""
Module containing functions for the calculation of associations used by 
ValPAS.
"""

from io import TextIOBase
from os import PathLike
from pathlib import Path
from typing import Literal

import pandas as pd


from ...utils.post_processing import rm_duplicates
from ...utils.post_processing import idx_name
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

        if self.omic_y.type is None:
            self.omic_x.type = "_".join([self.omic_x.type, "1"])
            self.omic_y.type = "_".join([self.omic_y.type, "2"])

        self.values = rm_duplicates(
            df=self.values,
            idx1=self.omic_x.features,
            idx2=self.omic_y.features,
        )

        self.counts = rm_duplicates(
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
