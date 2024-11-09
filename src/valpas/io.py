"""
_summary_
"""

from io import TextIOBase
from os import PathLike
from pathlib import Path
import sys
from typing import Literal
from typing import TextIO
from typing import BinaryIO
from warnings import warn

import pandas as pd
from pandas import ExcelWriter
import numpy as np

from .utils.post_processing import beautify_series
from . import Experiment

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


def import_experiments(
        source: Literal['from_files', 'from_folder'],
        path: str|PathLike|Path,
        file_type: Literal['csv', 'xlsx'],
        path2: str|PathLike|Path|None=None,
        sheet_names: list|None=None,
        ) -> list[Experiment]:
    pass



def import_from_folder(
        path: PathLike | Path, 
        file_type: Literal['csv', 'xlsx'],
        sheet_names: list=None,
        ) -> list[Experiment]:
    ret_dict = {}
    for child in path.glob(f'*.{file_type}'):
        if file_type == 'csv':
            experiment_name, omic_type = child.name.rsplit(
                sep="__", maxsplit=1
                )
            values = _import_csv(child.absolute())
            if experiment_name not in ret_dict:
                experiment = Experiment(
                    name=experiment_name,
                    omic_x_values=values,
                    omic_x_type=omic_type,
                    omic_x_features=values.index
                )
            else:
                experiment = ret_dict[experiment_name]
                experiment.omic_y_values = values
                experiment.omic_y_type = omic_type
                experiment.omic_y_features = values.index
            ret_dict[experiment_name] = experiment
        elif file_type == 'xlsx':
            experiment_name = child.name
            if sheet_names is None:
                raise ValueError(
                    f"'sheet_names' must not be 'None' if file_type 'xlsx' is"
                    f"chosen. Contents of 'sheet_names': {sheet_names}"
                )
            for sheet_name in sheet_names:
                values = _import_xls(child, sheet=sheet_name)
                omic_type = sheet_name
                if experiment_name not in ret_dict:
                    experiment = Experiment(
                        name=experiment_name,
                        omic_x_values=values,
                        omic_x_type=omic_type,
                        omic_x_features=values.index
                    )
                else:
                    experiment = ret_dict[experiment_name]
                    experiment.omic_y_values = values
                    experiment.omic_y_type = omic_type
                    experiment.omic_y_features = values.index
                ret_dict[experiment_name] = experiment

    return list(ret_dict.values())

def import_from_files(
        filepath: PathLike | Path,
        file_type: Literal['csv', 'xlsx'],
        filepath_2: (str | PathLike | Path )=None,
        sheet_names: str=None,
        ) -> dict[str, pd.DataFrame]:
    

    if file_type == 'csv':
        experiment_name, omic_x_type = filepath.name.rsplit(
            sep="__", maxsplit=1
        )
        omic_x_values = _import_csv(filepath_or_buffer=filepath)
        omic_x_features = omic_x_values.index

        if filepath_2 is not None:
            experiment_name, omic_y_type = filepath.name.rsplit(
                sep="__", maxsplit=1
            )
            omic_y_values = _import_csv(filepath_or_buffer=filepath_2)
            omic_y_features = omic_y_values.index
            experiment = Experiment(
                name=experiment_name,
                omic_x_values=omic_x_values,
                omic_x_type=omic_x_type,
                omic_x_features=omic_x_features,
                omic_y_values=omic_y_values,
                omic_y_type=omic_y_type,
                omic_y_features=omic_y_features
            )
        else:
            experiment = Experiment(
                name=experiment_name,
                omic_x_values=omic_x_values,
                omic_x_type=omic_x_type,
                omic_x_features=omic_x_features
            )
            
    elif file_type == 'xlsx':
        if sheet_names is None:
            raise ValueError(
                f"'sheet_names' must be defined if file_type=='xlsx'."
                f"sheet_names: '{sheet_names}'"
                )
        experiment_name = filepath.name
        omic_x_values = _import_xls(
            filepath_or_buffer=filepath,
            sheet=sheet_names[0]
            )
        omic_x_type = sheet_names[0]
        omic_x_features = omic_x_values.index
        if len(sheet_names) != 1:
            omic_y_values = _import_xls(
                filepath_or_buffer=filepath,
                sheet=sheet_names[1]
                )
            omic_y_type = sheet_names[1]
            omic_y_features = omic_y_values.index
            experiment = Experiment(
                name=experiment_name,
                omic_x_values=omic_x_values,
                omic_x_type=omic_x_type,
                omic_x_features=omic_x_features,
                omic_y_values=omic_y_values,
                omic_y_type=omic_y_type,
                omic_y_features=omic_y_features
            )
        else:
            experiment = Experiment(
                name=experiment_name,
                omic_x_values=omic_x_values,
                omic_x_type=omic_x_type,
                omic_x_features=omic_x_features
            )

    return list([experiment])


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
     

def _import_csv(filepath_or_buffer: str | PathLike | TextIO) -> pd.DataFrame:
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


def _import_xls(
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