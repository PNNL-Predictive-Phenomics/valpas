"""
_summary_
"""

import pandas as pd

class Omic():

    def __init__(
            self,
            type: str,
            features: pd.Index,
            ) -> None:
        
        self.type = type
        self.features = features

    @property
    def type(self):
        return self._type
    
    @type.setter
    def type(self, value):
        self._type = value

    @type.deleter
    def type(self):
        del self._type

    @property
    def features(self):
        return self._features
    
    @features.setter
    def features(self, value):
        self._features = value

    @features.deleter
    def features(self):
        del self._features


class OmicMeasurement(Omic):

    def __init__(
            self,
            type: str,
            measurements: pd.DataFrame,
            features: pd.Index,
            ) -> None:
        
        super().__init__(type, features)

        self.measurements = measurements


    @property
    def measurements(self):
        return self._measurements
    
    @measurements.setter
    def measurements(self, value):
        self._measurements = value
    
    @measurements.deleter
    def measurements(self):
        del self._measurements
