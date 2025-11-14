import pandas as pd
import numpy as np
import os
from typing import Union, List, Optional, Dict, Tuple
import warnings
warnings.filterwarnings('ignore')

class AnnotationList:
    def __init__(self,
                filepath: str = None,
                annotations: pd.DataFrame = None,
                primary_id_column: str = "id",
                primary_annotation_column: str = "annotation",
                extra_columns: List[str] = None,
                **kwargs)
        self.primary_id_column = primary_id_column
        self.primary_annotation_column = primary_annotation_column
        self.validation_report = {}

        if filepath and annotations == None:
            annotations, validation_report = self.read_annotation_file(filepath, primary_id_column,
                                                            primary_annotation_column, **kwargs)
        self.annotations = annotations
        self.validation_report = validation_report

    def read_annotation_file(self,
        filepath: str,
        primary_id_column: str,
        primary_annotation_column: str,
        required_columns: List[str] = None,
        optional_columns: List[str] = None,
        delimiter: str = None,
        sheet_name: Union[str, int] = 0,
        header: Union[int, List[int]] = 0,
        skiprows: int = None,
        na_values: Union[str, List[str]] = None,
        dtype: Dict[str, str] = None,
        encoding: str = 'utf-8',
        validate_ids: bool = True,
        remove_duplicates: str = 'warn',
        handle_missing_annotations: str = 'keep',
        strip_whitespace: bool = True,
        case_sensitive: bool = True,
        verbose: bool = True,
        **read_kwargs
        ) -> Tuple[pd.DataFrame, Dict]:
        """
        Read and validate an annotation file from various formats

        Args:
            filepath: Path to the annotation file (CSV, TSV, Excel)
            primary_id_column: Name of the primary identifier column (required)
            primary_annotation_column: Name of the primary annotation column (required)
            required_columns: List of additional required column names
            optional_columns: List of optional column names to include if present
            delimiter: File delimiter (auto-detected if None)
            sheet_name: Excel sheet name or index (default: 0 for first sheet)
            header: Row to use as column names (default: 0)
            skiprows: Number of rows to skip at start of file
            na_values: Additional strings to recognize as NA/NaN
            dtype: Dictionary of column data types
            encoding: File encoding (default: 'utf-8')
            validate_ids: Whether to validate primary IDs for duplicates/missing
            remove_duplicates: How to handle duplicate IDs ('keep_first', 'keep_last', 'remove', 'error', 'warn')
            handle_missing_annotations: How to handle missing annotations ('keep', 'remove', 'error', 'warn')
            strip_whitespace: Whether to strip whitespace from string columns
            case_sensitive: Whether column name matching is case-sensitive
            verbose: Whether to print progress and warnings
            **read_kwargs: Additional arguments passed to pandas read functions

        Returns:
            Tuple of (dataframe, validation_report)

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If required columns are missing or validation fails
            pd.errors.EmptyDataError: If file is empty
        """

        if verbose:
            print(f"Reading annotation file: {filepath}")

        # Validate file exists
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Annotation file not found: {filepath}")

        # Initialize validation report
        validation_report = {
            'file_path': filepath,
            'file_size_mb': os.path.getsize(filepath) / (1024 * 1024),
            'read_successfully': False,
            'columns_found': [],
            'columns_missing': [],
            'warnings': [],
            'errors': [],
            'data_issues': {},
            'final_shape': None,
            'processing_summary': {}
        }

        try:
            # Determine file type and read accordingly
            file_ext = os.path.splitext(filepath)[1].lower()

            if verbose:
                print(f"Detected file type: {file_ext}")

            # Read the file based on extension
            if file_ext in ['.xlsx', '.xls']:
                df = _read_excel_file(filepath, sheet_name, header, skiprows, na_values,
                                    encoding, read_kwargs, verbose)
            elif file_ext in ['.csv', '.tsv', '.txt']:
                df = _read_text_file(filepath, delimiter, file_ext, header, skiprows,
                                   na_values, encoding, read_kwargs, verbose)
            else:
                # Try to auto-detect format
                if verbose:
                    print(f"Unknown file extension '{file_ext}', attempting auto-detection...")
                df = _read_text_file(filepath, delimiter, file_ext, header, skiprows,
                                   na_values, encoding, read_kwargs, verbose)

            validation_report['read_successfully'] = True
            validation_report['initial_shape'] = df.shape

            if verbose:
                print(f"Successfully read file with shape: {df.shape}")
                print(f"Columns found: {list(df.columns)}")

        except Exception as e:
            validation_report['errors'].append(f"Failed to read file: {str(e)}")
            raise pd.errors.EmptyDataError(f"Could not read annotation file: {str(e)}")

        # Validate and process the dataframe
        df, validation_report = _validate_and_process_dataframe(
            df=df,
            primary_id_column=primary_id_column,
            primary_annotation_column=primary_annotation_column,
            required_columns=required_columns,
            optional_columns=optional_columns,
            validation_report=validation_report,
            validate_ids=validate_ids,
            remove_duplicates=remove_duplicates,
            handle_missing_annotations=handle_missing_annotations,
            strip_whitespace=strip_whitespace,
            case_sensitive=case_sensitive,
            dtype=dtype,
            verbose=verbose
        )

        # Final validation report updates
        validation_report['final_shape'] = df.shape
        validation_report['processing_summary'] = {
            'rows_processed': df.shape[0],
            'columns_retained': df.shape[1],
            'primary_ids_unique': df[primary_id_column].nunique(),
            'annotations_non_null': df[primary_annotation_column].notna().sum(),
            'success': len(validation_report['errors']) == 0
        }

        if verbose:
            _print_validation_summary(validation_report)

        # Raise error if critical issues found
        if validation_report['errors']:
            error_msg = f"Validation failed with {len(validation_report['errors'])} errors:\n"
            error_msg += "\n".join([f"- {error}" for error in validation_report['errors']])
            raise ValueError(error_msg)

        return df, validation_report

    def _read_excel_file(self, filepath: str, sheet_name: Union[str, int], header: Union[int, List[int]],
                        skiprows: int, na_values: Union[str, List[str]], encoding: str,
                        read_kwargs: Dict, verbose: bool) -> pd.DataFrame:
        """Read Excel file with error handling"""

        try:
            # Check available sheets first
            excel_file = pd.ExcelFile(filepath)
            available_sheets = excel_file.sheet_names

            if verbose:
                print(f"Available Excel sheets: {available_sheets}")

            # Validate sheet name
            if isinstance(sheet_name, str):
                if sheet_name not in available_sheets:
                    raise ValueError(f"Sheet '{sheet_name}' not found. Available: {available_sheets}")
            elif isinstance(sheet_name, int):
                if sheet_name >= len(available_sheets):
                    raise ValueError(f"Sheet index {sheet_name} out of range. Available: 0-{len(available_sheets)-1}")

            # Read Excel file
            df = pd.read_excel(
                filepath,
                sheet_name=sheet_name,
                header=header,
                skiprows=skiprows,
                na_values=na_values,
                **read_kwargs
            )

            return df

        except Exception as e:
            raise pd.errors.EmptyDataError(f"Error reading Excel file: {str(e)}")

    def _read_text_file(self, filepath: str, delimiter: str, file_ext: str, header: Union[int, List[int]],
                       skiprows: int, na_values: Union[str, List[str]], encoding: str,
                       read_kwargs: Dict, verbose: bool) -> pd.DataFrame:
        """Read text file (CSV, TSV, etc.) with auto-detection"""

        # Auto-detect delimiter if not specified
        if delimiter is None:
            delimiter = _detect_delimiter(filepath, file_ext, verbose)

        try:
            df = pd.read_csv(
                filepath,
                delimiter=delimiter,
                header=header,
                skiprows=skiprows,
                na_values=na_values,
                encoding=encoding,
                **read_kwargs
            )

            return df

        except Exception as e:
            raise pd.errors.EmptyDataError(f"Error reading text file: {str(e)}")

    def _detect_delimiter(self, filepath: str, file_ext: str, verbose: bool) -> str:
        """Auto-detect file delimiter"""

        # Default delimiters based on extension
        if file_ext == '.csv':
            default_delimiter = ','
        elif file_ext in ['.tsv', '.txt']:
            default_delimiter = '\t'
        else:
            default_delimiter = '\t'

        # Try to detect delimiter by reading first few lines
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()

            # Count occurrences of common delimiters
            delimiters = ['\t', ',', ';', '|', ' ']
            delimiter_counts = {delim: first_line.count(delim) for delim in delimiters}

            # Choose delimiter with highest count (if > 0)
            best_delimiter = max(delimiter_counts.items(), key=lambda x: x[1])

            if best_delimiter[1] > 0:
                detected_delimiter = best_delimiter[0]
                if verbose:
                    print(f"Auto-detected delimiter: '{detected_delimiter}' (found {best_delimiter[1]} occurrences)")
                return detected_delimiter
            else:
                if verbose:
                    print(f"No clear delimiter detected, using default: '{default_delimiter}'")
                return default_delimiter

        except Exception:
            if verbose:
                print(f"Delimiter detection failed, using default: '{default_delimiter}'")
            return default_delimiter

    def _validate_and_process_dataframe(self,
        required_columns: List[str],
        optional_columns: List[str],
        validation_report: Dict,
        validate_ids: bool,
        remove_duplicates: str,
        handle_missing_annotations: str,
        strip_whitespace: bool,
        case_sensitive: bool,
        dtype: Dict[str, str],
        verbose: bool
    ) -> Tuple[pd.DataFrame, Dict]:
        """Validate and process the loaded dataframe"""
        df = self.annotations
        primary_id_column = self.primary_id_column
        primary_annotation_column = self.primary_annotation_column

        # Handle case sensitivity for column names
        if not case_sensitive:
            column_mapping = {col: col for col in df.columns}
            df_lower_cols = [col.lower() for col in df.columns]

            # Check primary columns (case insensitive)
            primary_id_lower = primary_id_column.lower()
            primary_annotation_lower = primary_annotation_column.lower()

            if primary_id_lower not in df_lower_cols:
                validation_report['errors'].append(f"Primary ID column '{primary_id_column}' not found (case insensitive)")
            else:
                actual_id_col = df.columns[df_lower_cols.index(primary_id_lower)]
                if actual_id_col != primary_id_column:
                    if verbose:
                        print(f"Found primary ID column with different case: '{actual_id_col}'")
                    primary_id_column = actual_id_col

            if primary_annotation_lower not in df_lower_cols:
                validation_report['errors'].append(f"Primary annotation column '{primary_annotation_column}' not found (case insensitive)")
            else:
                actual_annotation_col = df.columns[df_lower_cols.index(primary_annotation_lower)]
                if actual_annotation_col != primary_annotation_column:
                    if verbose:
                        print(f"Found primary annotation column with different case: '{actual_annotation_col}'")
                    primary_annotation_column = actual_annotation_col

        else:
            # Case sensitive validation
            if primary_id_column not in df.columns:
                validation_report['errors'].append(f"Primary ID column '{primary_id_column}' not found")

            if primary_annotation_column not in df.columns:
                validation_report['errors'].append(f"Primary annotation column '{primary_annotation_column}' not found")

        # Stop here if primary columns are missing
        if validation_report['errors']:
            return df, validation_report

        # Validate additional required columns
        missing_required = []
        if required_columns:
            for req_col in required_columns:
                if case_sensitive:
                    if req_col not in df.columns:
                        missing_required.append(req_col)
                else:
                    req_col_lower = req_col.lower()
                    df_lower_cols = [col.lower() for col in df.columns]
                    if req_col_lower not in df_lower_cols:
                        missing_required.append(req_col)

        if missing_required:
            validation_report['errors'].append(f"Required columns missing: {missing_required}")
            return df, validation_report

        # Identify optional columns that are present
        present_optional = []
        if optional_columns:
            for opt_col in optional_columns:
                if case_sensitive:
                    if opt_col in df.columns:
                        present_optional.append(opt_col)
                else:
                    opt_col_lower = opt_col.lower()
                    df_lower_cols = [col.lower() for col in df.columns]
                    if opt_col_lower in df_lower_cols:
                        actual_col = df.columns[df_lower_cols.index(opt_col_lower)]
                        present_optional.append(actual_col)

        validation_report['columns_found'] = list(df.columns)
        validation_report['columns_missing'] = missing_required
        validation_report['optional_columns_present'] = present_optional

        # Select relevant columns
        columns_to_keep = [primary_id_column, primary_annotation_column]
        if required_columns:
            columns_to_keep.extend([col for col in required_columns if col in df.columns])
        if present_optional:
            columns_to_keep.extend(present_optional)

        # Remove duplicates from columns_to_keep
        columns_to_keep = list(dict.fromkeys(columns_to_keep))
        df = df[columns_to_keep]

        # Strip whitespace if requested
        if strip_whitespace:
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.strip()
                    # Convert back 'nan' strings to actual NaN
                    df[col] = df[col].replace('nan', np.nan)

        # Apply data types if specified
        if dtype:
            for col, col_type in dtype.items():
                if col in df.columns:
                    try:
                        df[col] = df[col].astype(col_type)
                    except Exception as e:
                        validation_report['warnings'].append(f"Could not convert column '{col}' to {col_type}: {str(e)}")

        # Validate primary IDs
        if validate_ids:
            validation_report['data_issues']['primary_id'] = _validate_primary_ids(
                df, primary_id_column, remove_duplicates, verbose
            )

            # Handle duplicates based on remove_duplicates parameter
            if validation_report['data_issues']['primary_id']['n_duplicates'] > 0:
                if remove_duplicates == 'error':
                    validation_report['errors'].append(
                        f"Duplicate primary IDs found: {validation_report['data_issues']['primary_id']['n_duplicates']}"
                    )
                    return df, validation_report
                elif remove_duplicates == 'keep_first':
                    df = df.drop_duplicates(subset=[primary_id_column], keep='first')
                    if verbose:
                        print(f"Removed duplicate IDs, keeping first occurrence")
                elif remove_duplicates == 'keep_last':
                    df = df.drop_duplicates(subset=[primary_id_column], keep='last')
                    if verbose:
                        print(f"Removed duplicate IDs, keeping last occurrence")
                elif remove_duplicates == 'remove':
                    df = df[~df.duplicated(subset=[primary_id_column], keep=False)]
                    if verbose:
                        print(f"Removed all duplicate IDs")
                elif remove_duplicates == 'warn':
                    validation_report['warnings'].append(
                        f"Found {validation_report['data_issues']['primary_id']['n_duplicates']} duplicate primary IDs"
                    )

        # Handle missing annotations
        missing_annotations = df[primary_annotation_column].isna().sum()
        if missing_annotations > 0:
            validation_report['data_issues']['missing_annotations'] = {
                'count': missing_annotations,
                'percentage': (missing_annotations / len(df)) * 100
            }

            if handle_missing_annotations == 'error':
                validation_report['errors'].append(f"Missing annotations found: {missing_annotations}")
                return df, validation_report
            elif handle_missing_annotations == 'remove':
                df = df.dropna(subset=[primary_annotation_column])
                if verbose:
                    print(f"Removed {missing_annotations} rows with missing annotations")
            elif handle_missing_annotations == 'warn':
                validation_report['warnings'].append(f"Found {missing_annotations} missing annotations")

        # Additional data quality checks
        validation_report['data_issues'].update(_perform_data_quality_checks(df, primary_id_column, primary_annotation_column))

        return df, validation_report

    def _validate_primary_ids(self, remove_duplicates: str, verbose: bool) -> Dict:
        """Validate primary ID column"""
        df = self.annotations

        id_validation = {
            'total_ids': len(df),
            'unique_ids': df[self.primary_id_column].nunique(),
            'missing_ids': df[self.primary_id_column].isna().sum(),
            'empty_ids': 0,
            'n_duplicates': 0,
            'duplicate_ids': []
        }

        # Check for empty string IDs
        if df[self.primary_id_column].dtype == 'object':
            empty_mask = (df[self.primary_id_column] == '') | (df[self.primary_id_column] == ' ')
            id_validation['empty_ids'] = empty_mask.sum()

        # Check for duplicates
        duplicated_mask = df.duplicated(subset=[self.primary_id_column], keep=False)
        id_validation['n_duplicates'] = duplicated_mask.sum()

        if id_validation['n_duplicates'] > 0:
            duplicate_ids = df.loc[duplicated_mask, self.primary_id_column].unique().tolist()
            id_validation['duplicate_ids'] = duplicate_ids[:10]  # First 10 duplicates

        return id_validation

    def _perform_data_quality_checks(self) -> Dict:
        """Perform additional data quality checks"""

        quality_checks = {}

        # Check annotation diversity
        unique_annotations = df[self.primary_annotation_column].nunique()
        total_non_null = df[self.primary_annotation_column].notna().sum()

        quality_checks['annotation_diversity'] = {
            'unique_annotations': unique_annotations,
            'total_non_null_annotations': total_non_null,
            'diversity_ratio': unique_annotations / total_non_null if total_non_null > 0 else 0
        }

        # Check for potential encoding issues
        if df[self.primary_annotation_column].dtype == 'object':
            annotations = df[self.primary_annotation_column].dropna().astype(str)

            # Check for unusual characters
            unusual_chars = annotations.str.contains(r'[^\w\s\-\.\,\;\:\(\)]', regex=True).sum()
            quality_checks['encoding_issues'] = {
                'rows_with_unusual_chars': unusual_chars,
                'percentage': (unusual_chars / len(annotations)) * 100 if len(annotations) > 0 else 0
            }

        # Check ID format consistency
        if df[self.primary_id_column].dtype == 'object':
            ids = df[self.primary_id_column].dropna().astype(str)

            # Basic format checks
            quality_checks['id_format'] = {
                'contains_spaces': ids.str.contains(' ').sum(),
                'contains_special_chars': ids.str.contains(r'[^\w\-\.]', regex=True).sum(),
                'average_length': ids.str.len().mean(),
                'length_std': ids.str.len().std()
            }

        return quality_checks

    def _print_validation_summary(self, validation_report: Dict):
        """Print a summary of the validation results"""

        print("\n" + "="*60)
        print("ANNOTATION FILE VALIDATION SUMMARY")
        print("="*60)

        print(f"File: {validation_report['file_path']}")
        print(f"File size: {validation_report['file_size_mb']:.2f} MB")
        print(f"Final shape: {validation_report['final_shape']}")

        # Processing summary
        summary = validation_report['processing_summary']
        print(f"\nProcessing Summary:")
        print(f"  Rows processed: {summary['rows_processed']}")
        print(f"  Columns retained: {summary['columns_retained']}")
        print(f"  Unique primary IDs: {summary['primary_ids_unique']}")
        print(f"  Non-null annotations: {summary['annotations_non_null']}")

        # Warnings
        if validation_report['warnings']:
            print(f"\nWarnings ({len(validation_report['warnings'])}):")
            for warning in validation_report['warnings']:
                print(f"  - {warning}")

        # Errors
        if validation_report['errors']:
            print(f"\nErrors ({len(validation_report['errors'])}):")
            for error in validation_report['errors']:
                print(f"  - {error}")

        # Data quality issues
        if 'data_issues' in validation_report:
            issues = validation_report['data_issues']

            if 'primary_id' in issues:
                id_issues = issues['primary_id']
                print(f"\nID Quality:")
                print(f"  Total IDs: {id_issues['total_ids']}")
                print(f"  Unique IDs: {id_issues['unique_ids']}")
                print(f"  Duplicates: {id_issues['n_duplicates']}")
                print(f"  Missing IDs: {id_issues['missing_ids']}")

            if 'annotation_diversity' in issues:
                ann_div = issues['annotation_diversity']
                print(f"\nAnnotation Quality:")
                print(f"  Unique annotations: {ann_div['unique_annotations']}")
                print(f"  Diversity ratio: {ann_div['diversity_ratio']:.3f}")

        status = "✓ SUCCESS" if summary['success'] else "✗ FAILED"
        print(f"\nValidation Status: {status}")
        print("="*60)
