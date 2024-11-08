"""
Module containing helper functions to deal with data handling (i.e. 
input & output).
"""


import sys

from pathlib import Path
from typing import Literal
from typing import TextIO
from typing import BinaryIO
from os import PathLike
from io import TextIOBase
from warnings import warn

import pandas as pd
import numpy as np

from pandas import ExcelWriter

from .post_processing import beautify_series
from .post_processing import sort_associations


class Experiment:
    """
    Custom Class that stores experiment data.

    Attributes
    ----------
    values: pandas.DataFrame
        DataFrame containing the raw values extracted from an
        experimental setup
    omic_x_type: str
        Name of the omics type that has been evaluated in the experiment
    omic_x_features: pandas.Index
        Contains all features / items of the omics type x that were 
        extracted
    omic_y_type: str, default = None
        Optional name of a second omics type that has been evaluated in
        the experiment. If not defined (i.e. _None_) the assumption is
        that associations among only one omics type (`omic_y_type`)
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
            values: pd.DataFrame,
            omic_x_type: str,
            omic_x_features: pd.Index,
            omic_y_type: str=None,
            omic_y_features: pd.Index=None,
            ):
        self.values = values
        self.omic_x_type = omic_x_type
        self.omic_x_features = omic_x_features
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


def reduce_to_shared_conditions(
        df_1: pd.DataFrame, df_2: pd.DataFrame
        ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ 
    This function operates on already inmported and transposed 
    pd.DataFrame objects. This means that the individual conditions in 
    the raw data (columns) are represented as rows (index).  

    .. deprecated:: 0
        ``reduce_to_shared_conditions`` no longer needed as separate
        function. ``prep_data`` performs merge / join on two imported 
        DataFrames which already contains this functionality.
    """
    intersect = df_1.columns.intersection(df_2.columns)
    df_1_ret = df_1.filter(items=intersect, axis="columns")
    df_2_ret = df_2.filter(items=intersect, axis="columns")

    df_1_ret.replace(0, np.nan, inplace=True)
    df_1_ret.dropna(axis="columns", how="all", inplace=True)
    df_1_ret.replace(np.nan, 0, inplace=True)

    df_2_ret.replace(0, np.nan, inplace=True)
    df_2_ret.dropna(axis="columns", how="all", inplace=True)
    df_2_ret.replace(np.nan, 0, inplace=True)
   
    return (df_1_ret, df_2_ret)


def export_csv(
        filepath_or_buffer: str | PathLike | Path | TextIOBase,
        data: pd.DataFrame,
        overwrite: bool=False,
        index : bool=True
        ) -> None:
    """
    Helper function to export computed DataFrame to csv formated plain 
    text.

    Parameters
    ----------
    filepath_or_buffer : str | PathLike | Path | TextIOBase
        Path to the \\*.csv that should be used for the export of data. 
        Can also be of type TextIOBase e.g. if the passed argument 
        is a stream to sys.stdout
    data : pandas.DataFrame
        Single pandas.DataFrame that contains the data to be stored.
    overwrite : bool, default=False
        If passed to the function as 'True', then the csv-file that is 
        pointed to by ``filepath_or_buffer`` will be overwritten if it 
        already exists.
    index: bool, default=True
        Passed to ``pd.DataFrame.to_csv``. Determines if the index (
        row names) should be written to the output.
    
    Returns
    -------
    None

    Raises
    ------
    FileExistsError
        If file pointed to by ``filepath_or_buffer`` already exists and 
        `overwrite==False`
    TypeError
        If ``filepath_or_buffer`` passed to function is not of a 'legal'
        type. 
    """

    # check if filepath is of 'legal' type
    if not isinstance(filepath_or_buffer,
                      (str, PathLike, Path, TextIOBase)):
        raise TypeError(
            f"filepath_or_buffer must be of type str, PathLike or Path."
            f" Supplied argument is of type {type(filepath_or_buffer)}."
        )
    
    # making sure that the filepath_or_buffer does not point to an
    # existing file and overwrite has been set to False
    if not isinstance(filepath_or_buffer, TextIOBase):
        filepath_or_buffer_ = Path(filepath_or_buffer).absolute()
        if filepath_or_buffer_.is_file() and not overwrite:
            raise FileExistsError(
                f"File '{filepath_or_buffer_}' already exists. If you want to "
                f"overwrite the file please specify so with argument "
                f"-O/--overwrite_output."
            )
    else:
        filepath_or_buffer_ = filepath_or_buffer
    # if filepath_or_buffer points to a new file, overwrite==True or the
    # output is written to stdout then write the file
    data.to_csv(filepath_or_buffer_, encoding='utf-8', index=index)

    return None


def export_xlsx(
        filepath: str | PathLike | Path,
        dfs: pd.DataFrame | list[pd.DataFrame],
        sheets: str | list[str],
        overwrite=False
        ) -> None:
    """
    Helper function to export computed DataFrame(s) to an Excel file

    Parameters
    ----------
    filepath : str | PathLike | Path
        Path to \\*.xlsx file that should be used for the export of data
    dfs : pandas.DataFrame | list[pandas.DataFrame]
        Either a single pandas.DataFrame object or a list of objects. 
        If a list is passed to the function, **sheets** must also be a 
        list and the number of elements in both must be identical.
    sheets : str | list[str]
        Either a single String or a list of Strings containing the names
        that the sheets should be stored as in the \\*.xlsx file. If a 
        list is passed to the function, **dfs** also needs to be a list
        and both need to contain the same number of elements.
    overwrite : bool, default=False
        Indicates if sheets should be overwritten if they already exist
        in the \\*.xlsx file that is passed to the function.

    Returns
    -------
    None

    Raises
    ------
    TypeError
        If the passed filepath is not the correct type
    TypeError
        If dfs or sheets is not the correct type or they don't match
        in type (e.g. type(dfs)==list & type(sheets)==str)
    ValueError
        If both dfs and sheets are of type list, but the don't hold the
        same number of items.
    """

    # check to make sure the filepath passed to the function is 'legal'
    if not isinstance(filepath, (str, PathLike, Path)):
        raise TypeError(
            f"filepath must be of type str, PathLike or Path. "
            f"Supplied argument is of type {type(filepath)}."
        )
    else:
        # determining the mode to pass to ExcelWriter depending on 
        # whether the file already exists
        filepath_ = Path(filepath).absolute()
        if filepath_.is_file():
            mode = 'a'
        else:
            mode = 'w'
    
    # 'translating' the strategy of what to do if a give sheet already
    # exists in the xlsx file (if xlsx is also already present) for 
    # later use  
    if overwrite:
        if_sheet_exists_ = 'replace'
    else:
        if_sheet_exists_ = 'error'


    # if only one DF needs to be saved we cast dfs and sheets into lists 
    # with only one element each to consolidate ExcelWriter calls 
    if isinstance(dfs, pd.DataFrame) and isinstance(sheets, str):
        dfs = [dfs]
        sheets = [sheets]
            
    # Main logic saving the DataFrame(s) into (a) Sheet(s). The else
    # blocks (raising Errors) are only called if dfs and sheets contain
    # unexpected variable types
    if isinstance(dfs, list) and isinstance(sheets, list):
        
        # Make sure that both dfs and sheets contain the same number of 
        # elements
        if len(dfs) != len(sheets):
            raise ValueError(
                f"Number of DataFrames to write to {filepath_} does "
                "not match number of supplied Sheet names."
            )
        # If we append to the Excel file (we previously checked if the 
        # Excel file passed to the function exsits) we need to define 
        # additional parameters in the ExcelWriter call. Specifically 
        # we need to add the information whether already exsisting
        # Sheets should be overwritten.
        if mode == 'a':
            try:
                with ExcelWriter(filepath_, mode='a',
                             if_sheet_exists=if_sheet_exists_) as writer:
                    for i in range(0, len(dfs)): # export all DFs
                        dfs[i].to_excel(writer, sheet_name=sheets[i])
            except ValueError as e:
                # This happens only if the sheet named already exists
                # and we didn't specify that the sheet should be
                # overwritten.
                sys.exit(
                    f"Sheet '{sheets[i]}' already exists in "
                    f"{filepath_}. Please choose a different sheet "
                    f"name or use -O/--overwrite_output, to overwrite "
                    f"contents in sheet '{sheets[i]}."
                )
        # If a new file is being generated we don't need to try/catch
        # the "exsisting sheet" error
        elif mode == 'w':
            with ExcelWriter(filepath_, mode='w') as writer:
                for i in range(0, len(dfs)):
                    dfs[i].to_excel(writer, sheet_name=sheets[i])
    
    # The remaining elif/else statements cover / raise exceptions if the
    # variables passed to the function are not 'legal'
    elif not (isinstance(dfs, list) or isinstance(dfs, pd.DataFrame)):
        raise TypeError(
            f"dfs must be either of type pandas.DataFrame or list. "
            f"Suppied dfs is of type {type(dfs)}."
        )
    elif not (isinstance(sheets, list) or isinstance(sheets, str)):
        raise TypeError(
            f"sheets must be either of type str or list. "
            f"Suppied sheets is of type {type(sheets)}."
        )
    else:
        raise TypeError(
            "dfs and sheets must type match."
        )
    
    return None


def import_asssociation_matrix(
        filepath: str | PathLike | Path,
        sheet: str | float=0,
        ) -> pd.DataFrame:
    """
    Imports a saved correlation / association matrix saved by 
    ``valpas.utils.write_outfile`` into a ``pandas.DataFrame`` object
    and returns it.

    Parameters
    ----------
    filepath : {str, PathLike, Path}
        The path to the file that should be imported
    sheet : str, default=None
        The sheet name to import the association matrix from if filepath
        points to an Excel file

    Returns
    -------
    pandas.DataFrame
        A pandas DataFrame that contains the association values in the 
        raw data file that was imported.

    Notes
    -----
    Can for example be used to read in data necessary to plot a heatmap 
    via the `valpas.visualize.heatmap` module. 
    """
    if not isinstance(filepath, Path):
        filepath = Path(filepath).absolute()

    f_suffix = filepath.suffix
    if f_suffix == ".xlsx":
        if sheet == 0:
            warn(
                f"No excel sheet indicated for import. Defaulting to import "
                f"the first sheet in the excel file '{filepath}'."
            )
        try:
            df = pd.read_excel(
                io=filepath,
                sheet_name=sheet,
                index_col=0,
            )
        except ValueError as err:
            raise err
        except FileNotFoundError as err:
            raise err
    elif f_suffix == ".csv":
        try:
            df = pd.read_csv(
                filepath_or_buffer=filepath,
                index_col=0,
                header=0,
            )
            df = df.map(lambda x: float(x.split(':')[0]))
        except FileNotFoundError as err:
            raise err
    else:
        raise ValueError(
            f"Supplied file is of type '{f_suffix}'. "
            "Expected '.csv' or '.xlsx'."
        )
    

    return df


def import_from_folder(
        path: str | PathLike | Path, 
        file_type: Literal['csv', 'xlsx'],
        sheet_names: list=None,
        ) -> dict[str, pd.DataFrame]:
    ret_dict = {}
    for child in path.glob(f'*.{file_type}'):
        if file_type == 'csv':
            df = import_csv(child.absolute())
            ret_dict[child.stem] = df
        elif file_type == 'xlsx':
            if sheet_names is None:
                raise ValueError(
                    f"'sheet_names' must not be 'None' if file_type 'xlsx' is"
                    f"chosen. Contents of 'sheet_names': {sheet_names}"
                )
            i = 0
            for sheet_name in sheet_names:
                df = import_xls(child, sheet=sheet_name)
                if sheet_name is not None:
                    ret_dict['_'.join([child.stem, sheet_name])] = df
                else:
                    ret_dict['_'.join([child.stem, str(i)])] = df
                    i = i+1
    
    return ret_dict

def import_from_files(
        filepath_or_buffer: str | PathLike | Path,
        filepath_or_buffer_2: (str | PathLike | Path )=None,
        sheet1: str=None,
        sheet2: str=None,
        ) -> dict[str, pd.DataFrame]:
    
    ret_dict = {}

    if not isinstance(filepath_or_buffer, Path):
        filepath_or_buffer = Path(filepath_or_buffer).absolute()

    f_suffix = filepath_or_buffer.suffix
    if f_suffix == '.xlsx':
        if sheet1 is None:
            raise ValueError(
                f"No Sheet name provided for file {filepath_or_buffer}"
            )
        df = import_xls(filepath_or_buffer=filepath_or_buffer, sheet=sheet1)
        ret_dict['_'.join([filepath_or_buffer.stem, sheet1])] = df
    elif f_suffix == '.csv':
        df = import_csv(filepath_or_buffer)
        ret_dict[filepath_or_buffer.stem] = df
    else: 
        raise ValueError(
            f"Supplied file is of type '{f_suffix}'. "
            "Expected '.csv' or '.xlsx'."
        )
    
    
    if filepath_or_buffer_2 is not None:
        if not isinstance(filepath_or_buffer_2, Path):
            filepath_or_buffer_2 = Path(filepath_or_buffer_2).absolute()

        f_suffix = filepath_or_buffer_2.suffix
        if f_suffix == '.xlsx':    
            if sheet2 is None:
                raise ValueError(
                    f"No Sheet name provided for file {filepath_or_buffer_2}"
                )
            df = import_xls(
                filepath_or_buffer=filepath_or_buffer_2, sheet=sheet2
                )
            ret_dict['_'.join([filepath_or_buffer_2.stem, sheet2])] = df
        elif f_suffix == '.csv':
            df = import_csv(filepath_or_buffer_2)
            ret_dict[filepath_or_buffer_2.stem] = df
        else:
            raise ValueError(
                f"Supplied file is of type '{f_suffix}'. "
                "Expected '.csv' or '.xlsx'."
            )
    elif sheet2 is not None and f_suffix == '.xlsx' and sheet1 != sheet2:
        df = import_xls(
            filepath_or_buffer=filepath_or_buffer, sheet=sheet2
            )
        ret_dict['_'.join([filepath_or_buffer.stem, sheet2])] = df

    return ret_dict
     

def import_csv(filepath_or_buffer: str | PathLike | TextIO) -> pd.DataFrame:
    """
    Imports a csv file. Returns a pandas DataFrame object containing 
    the data.

    Parameters
    ----------
    filepath_or_buffer: str | PathLike | TextIO
        Path to CSV file that should be imported
    
    Returns
    -------
    pd.DataFrame
        The contents of the imported CSV as a ``pandas.DataFrame``

    Raises
    ------
    FileNotFoundError
        If ``filepath_or_buffer`` points to file that does not exist.
    TypeError
        If ``filepath_or_buffer`` is not an instance of a 'legal' type.
    """
    filepath_or_buffer_ = filepath_or_buffer
    if isinstance(filepath_or_buffer_, (str, PathLike, TextIOBase)):
        try:
            df = pd.read_csv(
                filepath_or_buffer=filepath_or_buffer_,
                index_col=0,
            )
        except FileNotFoundError as err:
            raise FileNotFoundError(err)
    else:
        error = (
            f"filepath_or_buffer must be of type str, PathLike or TextIO. "
            f"Supplied argument is of type {type(filepath_or_buffer_)}."
            )
        raise TypeError(error)
    
    return df


def import_xls(
        filepath_or_buffer: str | PathLike | BinaryIO,
        sheet: str
        ) -> pd.DataFrame:
    """
    Imports a sheet within a xlsx file into a pandas DataFrame.

    Parameters
    ----------
    filepath_or_buffer: str | PathLike | BinaryIO
        Path (or Buffer) to the Excel file that should be imported
    sheet: str 
        The name of the sheet to be imported.
    
    Returns
    -------
    pandas.DataFrame
        containing the contents of the defined sheet
        
    Raises
    ------
    FileNotFoundError
        If ``filepath_or_buffer`` points to file that does not exist
    TypeError
        If ``filepath_or_buffer`` is not an instance of 'legal' type.
    """
    filepath_or_buffer_ = filepath_or_buffer
    if isinstance(filepath_or_buffer_, (str, PathLike, BinaryIO)):
        try:
            df = pd.read_excel(
                io=filepath_or_buffer_,
                sheet_name=sheet,
                index_col=0,
            )
        except FileNotFoundError as err:
            raise FileNotFoundError(err)
    else:
        error = (
            f"filepath_or_buffer must be of type str, PathLike or TextIO. "
            f"Supplied argument is of type {type(filepath_or_buffer_)}."
            )
        raise TypeError(error)
    
    return df


def prep_data(
        dfs: dict,
        filter_cutoff: float=0.9,
        cut: bool=False,
        threshold: float=None,
        ) -> tuple[pd.DataFrame, pd.Index, pd.Index]:
    """
    Imports data file(s) into pandas DataFrame. Can handle import from 
    one or two data files. If provided data files are Excel files, the 
    sheets from which to import also have to be defined.

    Parameters
    ----------
    filepath_or_buffer : str | PathLike | Path
        Defines the path to the main file to be imported and used as a 
        basis to calculate associations from. Can be CSV or Excel file.
        If ``filepath_or_buffer`` is an Excel file, ``sheet1`` needs to 
        be defined.
    filepath_or_buffer_2 : str | PathLike | Path, default = None
        Optinonal path definition to a second input file. If 
        ``filepath_or_buffer_2`` is defined, then associations between
        datapoints in ``filepath_or_buffer`` and ``filepath_or_buffer``
        are calculated. Note, if an Excel file is defined as input 
        ``sheet2`` needs to be defined.
    sheet1 : str, default = None
        Used to define the name of the Excel sheet that should be 
        imported. Only used when ``filepath_or_buffer`` points to an 
        Excel file.
    sheet2 : str, default = None
        See ``sheet1``. If ``filepath_or_buffer2`` is defined (and an 
        Excel file) the defined sheet will be imported from there. 
        Otherwise the sheet will be imported from ``filepath_or_buffer``.
    filter_cutoff : float, default = 0.9
        Rows in ``filepath_or_buffer(_2)`` need to contain at least the 
        fraction of ``filter_cutoff`` values that are not `0.0` or 
        `NaN`. Any rows that have less defined values will excluded from
        the calculation of the association value.
    cut : bool, default = False
        Determines if the values in the DataFrame should be binned for 
        further association calculations
    threshold : float, default = None
        Optional argument that defines the threshold values that is used
        for thresholding values.

    Returns
    -------
    tuple[pd.DataFrame, pd.Index, pd.Index]
        Return tuple contains three objects:
            1. a pandas DataFrame object containing transposed data
            2. a pandas Index object containing the index of the 
               DataFrame resulting from importing ``filepath_or_buffer``
            3. a pandas Index object containing the index of the 
               DataFrame resulting from importing 
               ``filepath_or_buffer_2`` or if ``filepath_or_buffer_2``
               was not passed to the function (i.e. `None`) then `None` 
               is returned as the 3rd position of the tuple

    Notes
    -----
    Imports data file(s) into pandas DataFrame object(s). If two data 
    files are provided, the two imported DataFrames are concatenated 
    over their shared columns (conditions). Finally, (depending on the 
    arguments passed to the function call) the resulting DataFrame is:

    - cleaned of low confidence items (rows) that contain to many 0 
      values.
    - binned (necessary for mutual information)
    - thresholded (necessary for Jaccard Index/Similarity)

    """

    # if not isinstance(filepath_or_buffer, Path):
    #     filepath_or_buffer = Path(filepath_or_buffer).absolute()

    # f_suffix = filepath_or_buffer.suffix
    # if f_suffix == '.xlsx':
    #     if sheet1 is None:
    #         raise ValueError(
    #             f"No Sheet name provided for file {filepath_or_buffer}"
    #         )
    #     df = import_xls(filepath_or_buffer=filepath_or_buffer, sheet=sheet1)
    # elif f_suffix == '.csv':
    #     df = import_csv(filepath_or_buffer)
    # else: 
    #     raise ValueError(
    #         f"Supplied file is of type '{f_suffix}'. "
    #         "Expected '.csv' or '.xlsx'."
    #     )
    
    # idx1 = df.index
    # idx2 = None

    # if filepath_or_buffer_2 is not None:
    #     if not isinstance(filepath_or_buffer_2, Path):
    #         filepath_or_buffer_2 = Path(filepath_or_buffer_2).absolute()

    #     f_suffix = filepath_or_buffer_2.suffix
    #     if f_suffix == '.xlsx':    
    #         if sheet2 is None:
    #             raise ValueError(
    #                 f"No Sheet name provided for file {filepath_or_buffer_2}"
    #             )
    #         df_2 = import_xls(
    #             filepath_or_buffer=filepath_or_buffer_2, sheet=sheet2
    #             )
    #     elif f_suffix == '.csv':
    #         df_2 = import_csv(filepath_or_buffer_2)
    #     else:
    #         raise ValueError(
    #             f"Supplied file is of type '{f_suffix}'. "
    #             "Expected '.csv' or '.xlsx'."
    #         )
    #     idx2 = df_2.index
    #     df = pd.concat([df, df_2], join='inner')
    
    # # routine that happens only if
    # # - only one infile has been defined
    # # - that file is an excel file (xlsx)
    # # - a second sheet has been defined as import
    # # - the second sheet is not the same as the first sheet  
    # # If those cases are satisfied, the additional sheet is imported and
    # # the concatenated DF is generated
    # elif sheet2 is not None and f_suffix == '.xlsx' and sheet1 != sheet2:
    #     df_2 = import_xls(
    #         filepath_or_buffer=filepath_or_buffer, sheet=sheet2
    #         )
    #     idx2 = df_2.index
    #     df = pd.concat([df, df_2], join='inner')

    if len(dfs) == 1:
        k, df = dfs.popitem()
        idx1 = df.index
        idx2 = None
    elif len(dfs) == 2:
        k, df1 = dfs.popitem()
        k, df2 = dfs.popitem()
        idx1 = df1.index
        idx2 = df2.index
        df = pd.concat([df1, df2], join='inner')
    else:
        raise NotImplementedError(
            "Handling more than 2 dfs is currently not implemented"
            )

    # removing low confidence items
    df, index = remove_low_confidence_items(df=df, cutoff=filter_cutoff)
    if len(index.values) > 0:
        print("Removed items: ", end="", file=sys.stderr)
        print(*index.values, sep=", ", file=sys.stderr)
        idx1_ret = idx1.difference(index)
        idx1_ret.name = idx1.name
        if idx2 is not None:
            idx2_ret = idx2.difference(index)
            idx2_ret.name = idx2.name
        else:
            idx2_ret = idx2
    # this is done if binning is necessary (e.g. for mutual information)
    if cut:
        df = bin(df=df)

    # this is done if thersholding is necessary (e.g. for jaccard dist)
    if threshold:
        df = threshold_df(df=df, threshold_rel=threshold)

    if idx2 is None:
        return (df.transpose(), idx1_ret, None)
    else:
        return (df.transpose(), idx1_ret, idx2_ret)


def bin(df: pd.DataFrame, num_bins: int=2) -> pd.DataFrame:
    """
    Helper function for binning the values of rows in a DataFrame

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame with values to be binned
    num_bins: int, default = 2
        Defines the number of bins.

    Returns
    -------
    pandas.DataFrame
        Return DataFrame with binned rows.
    """
    df = df.apply(
        lambda x: pd.cut(
            x, bins=num_bins,
            labels=range(0,num_bins)
            ),
        axis=0
        )
    return df


def threshold_df(df: pd.DataFrame, threshold_rel: float=0.5) -> pd.DataFrame:
    """
    Thresholds rows in a pd.DataFrame containing aboslute or relative 
    abunances for items (rows, e.g. metabolites) across different 
    conditions (columns).

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame that contains values that should be thresholded
    threshold_rel : float, default=0.5
        Relative threshold, that is to be used for the internal
        thresholding function. 

    Returns
    -------
    pandas.DataFrame
        A truth table encoded with 0s and 1s denoting if the value 
        falls above the determined threshold.

    Notes
    -----
    NA values in the DataFrame passed to the function will automatically
    be cast to 'False' / 0.
    
    Thresholding is done relative to the values recorded in the rows,
    i.e.

    .. math::

        t = min(v_{ij}) + (max(v_{ij}) - min(v_{ij})) * threshold\\_rel
    
    for :math:`v_{ij}` is any value :math:`v_i` in :math:`Row` :math:`j`
    """

    # it is assumed that the DF that is passed to the function will not
    # contain NaNs/NAs in place of 0s. If this is not the case the if 
    # statement below is triggered and 0s are replaced with NaN such 
    # that they don't interfere with calulating the threshold
    if df.eq(0).any(axis=None):
        df.replace(0, np.nan, inplace=True)
    
    # creating a Series containing thresholds for individual items
    # currently the threshold is calculated per item across different
    # conditions (axis = 1).
    s_thresh = (
        df.min(axis=1)
        + (df.max(axis=1) - df.min(axis=1)) * threshold_rel
    )
    
    # generating the return DataFrame
    # ATTN: DataFrame.ge() will return 'False' for NaNs
    # An additional step (see mask) is needed to cast NaNs back into 
    # the return DF.
    df_ret = (
        df
        .ge(s_thresh, axis='index') # check if cell satisfies the threshold
        .astype(int) # casts the boolean returned by `.gt()` to int(0,1)
        )
    df_ret.mask(df.isna(), df, inplace=True)
    
    return df_ret


def remove_low_confidence_items(df: pd.DataFrame, cutoff: float=0.9,
        drop_na_cols: bool=True) -> tuple[pd.DataFrame, pd.Index]:
    """
    Removes low confidence (to many NAs) 
    items (rows) from the DataFrame. The `cutoff` argument passed to 
    the function determines how complete (i.e. the fraction of non-NA 
    values) an item (row) needs to be to retained in the DataFrame.
    Additionally, the function can be told to keep any columns that 
    are completely populated with NAs/0s as a result of removing items 
    from the DataFrame. By default those columns are dropped.

    Parameters
    ----------
    df : pandas.DataFrame
        The DataFrame that should be filtered to remove low confidence
        items.
    cutoff : float, default=0.9
        The cutoff that determines if an item is considered a low 
        confidence item, i.e. if less than a fraction ``cutoff`` of 
        data points for an item are not NaN the item is considered low 
        confidence.
    drop_na_cols : bool, default=True
        If the removal of low confidence items generates new columns in 
        the DataFrame that are entirely made up of NaN values those 
        columns will be dropped if ``drop_na_cols`` is set to `True`.

    Returns
    -------
    tuple[pandas.DataFrame, pandas.Index]
        The return tuple contains two objects:
            1. The "clean" DataFrame
            2. An index of all dropped items

    """
    
    # treating '0' as NaNs for easier counting of missing values
    df.replace(0, np.nan, inplace=True)

    # creating an index of rows (items) to filter i.e. finding the rows
    # that where the fraction of NAs is larger than 1-cutoff
    s = (
        (df.isna() # create truth table whether values is NaN
         .sum(axis=1) # sum "True" iterating over columns for each row
         /df.shape[1]) # divide by the number of columns
         .gt(1-cutoff) # check if fraction of NAs (in row) is > cutoff
        )
    index = s[s].index # creating the actual index (i.e. which rows to drop)

    # filter the DataFrame
    df_filtered = df.drop(
        labels=index, # using the defined index from above
        axis='index', # drop based on rows
        )
    
    # if the above procedure generated columns (conditions) that contain
    # only NAs as values, those will be removed. The behaviour can be 
    # toggled with a function argument (default = True)
    if drop_na_cols:
        df_filtered.dropna(axis="columns", how="all", inplace=True)
    
    # return both the filtered df and the index of dropped items
    return (df_filtered, index)


def write_outfile(
        data: tuple[pd.DataFrame, pd.DataFrame],
        file_handle: str | PathLike | Path | TextIOBase, 
        idx: tuple[str, str],
        output_type: Literal[
            'sorted_list', 'correlation_matrix'
            ]='sorted_list',
        overwrite: bool=False,
        association_type: str='correlation',
        ) -> None:
    """
    Takes a ``pandas.DataFrame`` object and writes it to a file handle.
    This can be either a file or ``sys.stdout``.

    Parameters
    ----------
    data : tuple[pandas.DataFrame, pandas.DataFrame]
        Touple of two ``pandas.DataFrame``, one containing calculated
        association values the other counts for how many values were 
        used for the association value calculation between two omics 
        data points.
    file_handle : str | PathLike | Path | TextIOBase
        Path to the outfile that should be written.
    idx : tuple[str, str]
        Touple of two ``pandas.Index`` objects containing the index for 
        the two omics types which were used to calculate association 
        values.
    output_type : {'sorted_list', 'correlation_matrix'},\
                  default='sorted_list'
        The type of output file that should be written.
    overwrite : bool, default=False
        Defines if the output file / sheet should be overwritten if it 
        already exists.
    association_type : str, default='correlation'
        Optional argument that is used to describe the association type
        in the output.

    Raises
    ------
    ValueError
        If the supplied ``file_handle`` is not an instance of a 'legal'
        type.
    """

    if isinstance(file_handle, (str, PathLike, Path)):
        filepath_or_buffer = Path(file_handle).absolute()
        f_suffix = filepath_or_buffer.suffix
        if f_suffix == '.xlsx':
            f_type = 'xlsx'
        elif f_suffix == '.csv':
            f_type = 'csv'
        elif f_suffix == '.tsv':
            f_type = 'tsv'
        else:
            raise ValueError(
                f"Supplied file '{filepath_or_buffer} is of type '{f_suffix}'."
                f" Expected *.xlsx, *.csv or *.tsv."
            )
    elif isinstance(file_handle, TextIOBase):
        f_type = 'csv'
    else:
        raise Exception(
            f"Reached point that shouldn't be reachable. file_handle is of "
            f"type '{type(file_handle)}', which is not supported.")
    
    
    data_association = data[0]
    data_counts = data[1]

    # remove idx and cols from data_associations where all values are
    # NaN / None
    data_association.dropna(axis="index", how="all", inplace=True)
    data_association.dropna(axis="columns", how="all", inplace=True)
    
    # Do the same for data_counts by checking which cols in 
    # data_associations have been dropped
    cols_to_drop = data_counts.columns.difference(data_association.columns)
    idx_to_drop = data_counts.index.difference(data_association.index)
    data_counts.drop(labels=cols_to_drop.values, axis="columns", inplace=True)
    data_counts.drop(labels=idx_to_drop.values, axis="index", inplace=True)

    if f_type in ('csv', 'tsv') and output_type == 'sorted_list':
        data_association = beautify_series(df=data_association,
                                           value=association_type)
        data_counts = beautify_series(df=data_counts, value='counts')
        if f_type in ('csv', 'tsv'):
            data_ = data_association.merge(
                data_counts,
                on=[idx[0],idx[1]],
                how='inner'
                )
            export_csv(
                filepath_or_buffer=file_handle,
                data=data_,
                overwrite=overwrite,
                index=False
                )
    elif f_type in ('csv', 'tsv') and output_type == 'correlation_matrix':
        data_ = (
            data_association
                .round(decimals=5) # we only want to display 5 decimals
                .astype(str) # need to cast to String for concatenation 
            + ':' # concatenating using a ':' as field seperator 
            + data_counts.astype(str) # see above
        )
        export_csv(
            filepath_or_buffer=file_handle,
            data=data_,
            overwrite=overwrite
            )
    elif f_type == 'xlsx':
            if output_type == 'sorted_list':
                data_association = beautify_series(df=data_association,
                                                   value=association_type)
                data_counts = beautify_series(df=data_counts, value='counts')
            dfs = [data_association, data_counts]
            sheets = [
                f"assoc_{idx[0]}-{idx[1]}"[:30],
                f"count_{idx[0]}-{idx[1]}"[:30]
            ]
            export_xlsx(
                filepath=file_handle,
                dfs=dfs,
                sheets=sheets,
                overwrite=overwrite)
    else:
        raise Exception(
            f"Reached point that shouldn't be reachable. file_handle is of "
            f"type '{type(file_handle)}', which is not supported.")

