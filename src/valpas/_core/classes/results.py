"""
Module containing functions for the calculation of associations used by 
ValPAS.
"""

import pandas as pd

class AssociationResult():

    def __init__(
            self,
            values: pd.DataFrame,
            counts: pd.DataFrame,
            features_x: pd.Index,
            features_y: pd.Index,
            ) -> None:
        
        self.values = values
        self.counts = counts
        self.features_x = features_x
        self.features_y = features_y
    
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

    # features_x
    @property
    def features_x(self):
        return self._features_x
    
    @features_x.setter
    def features_x(self, value):
        self._features_x = value
    
    @features_x.deleter
    def features_x(self):
        del self._features_x

    # features_y
    @property
    def features_y(self):
        return self._features_y    
    
    @features_y.setter
    def features_y(self, value):
        self._features_y = value
    
    @features_y.deleter
    def features_y(self):
        del self._features_y

