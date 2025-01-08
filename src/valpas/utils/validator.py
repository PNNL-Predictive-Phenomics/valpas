
from itertools import combinations
import sys

from .. import SingleExperiment

def validate_input(e: list[SingleExperiment], **kwargs: dict):


    for e1, e2 in combinations(e, 2):
        
        e1_omic_x_name = e1.omic_x.measurements.index.name
        e1_omic_y_name = e1.omic_y.measurements.index.name
        e2_omic_x_name = e2.omic_x.measurements.index.name
        e2_omic_y_name = e2.omic_y.measurements.index.name
    
        overlap_fraction_warn = kwargs.get('overlap_fraction_warn', 0.8)
        # check if the omic types match
        omics_match = _check_omics_match(e1, e2)
        if not omics_match[0]:
            print(f"WARNING: Omic missmatch! - "
                  f"{e1.name}: '{e1_omic_x_name}' - "
                  f"{e2.name}: '{e2_omic_x_name}' - ",
                  file=sys.stderr
                 )
        if not omics_match[1]:
            print(f"WARNING: Omic missmatch! - "
                  f"{e1.name}: '{e1_omic_y_name}' - "
                  f"{e2.name}: '{e2_omic_y_name}' - ",
                  file=sys.stderr
                 )
        else:
            print(f"Matching Omics between '{e1.name}' & '{e2.name}'")

        # check how large the overlap between the omics of the two experiments is 
        omic_overlap = _check_omics_overlap(e1, e2)
        omic_x_overlap_num = len(omic_overlap[0])
        omic_y_overlap_num = len(omic_overlap[1])
        e1_omic_x_feature_num = len(e1.omic_x.measurements.index.to_list())
        e2_omic_x_feature_num = len(e2.omic_x.measurements.index.to_list())
        e1_omic_y_feature_num = len(e1.omic_y.measurements.index.to_list())
        e2_omic_y_feature_num = len(e2.omic_y.measurements.index.to_list())

        print(
            f"{e1_omic_x_name}/{e2_omic_x_name} features in both "
            f"experiments: '{e1.name}' ({omic_x_overlap_num}/"
            f"{e1_omic_x_feature_num}); "
            f"'{e2.name}' ({omic_x_overlap_num}/"
            f"{e2_omic_x_feature_num})",
            file=sys.stdout
            )
        print(
            f"{e1_omic_y_name}/{e2_omic_y_name} features in both "
            f"experiments: '{e1.name}' ({omic_y_overlap_num}/"
            f"{e1_omic_y_feature_num}); "
            f"'{e2.name}' ({omic_y_overlap_num}/"
            f"{e2_omic_y_feature_num})",
            file=sys.stdout
            )
        
        if (
            omic_x_overlap_num/e1_omic_x_feature_num < overlap_fraction_warn
            or omic_x_overlap_num/e2_omic_x_feature_num < overlap_fraction_warn
            ):
            
            print(
                f"WARNING: Low overlap of '{e1_omic_x_name}' between {e1.name}"
                f" & {e2.name}",
                file=sys.stderr
            )
        if (
            omic_y_overlap_num/e1_omic_y_feature_num < overlap_fraction_warn
            or omic_y_overlap_num/e2_omic_y_feature_num < overlap_fraction_warn
            ):
            
            print(
                f"WARNING: Low overlap of '{e1_omic_y_name}' between {e1.name}"
                f" & {e2.name}",
                file=sys.stderr
            )


        condition_overlap = _check_condition_overlap(e1, e2)
        condition_overlap_num = len(condition_overlap)

        if condition_overlap_num == 0:
            print(
                'WARNING: No overlapping conditions!',
                file=sys.stderr
                )
        



def _check_omics_match(
        e1: SingleExperiment,
        e2: SingleExperiment,
        ) -> bool:
    

    e1_index_omic_x = e1.omic_x.measurements.index
    e2_index_omic_x = e2.omic_x.measurements.index

    e1_index_omic_y = e1.omic_y.measurements.index
    e2_index_omic_y = e2.omic_y.measurements.index

    omic_x_identical = True if e1_index_omic_x.name == e2_index_omic_x.name else False
    omic_y_identical = True if e1_index_omic_y.name == e2_index_omic_y.name else False

    return (omic_x_identical, omic_y_identical)


def _check_omics_overlap(
        e1: SingleExperiment,
        e2: SingleExperiment,
        ) -> list:
    
    e1_index_omic_x = e1.omic_x.measurements.index
    e2_index_omic_x = e2.omic_x.measurements.index

    e1_index_omic_y = e1.omic_y.measurements.index
    e2_index_omic_y = e2.omic_y.measurements.index

    omic_x_overlap = e1_index_omic_x.intersection(e2_index_omic_x)
    omic_y_overlap = e1_index_omic_y.intersection(e2_index_omic_y)

    return (omic_x_overlap.to_list(), omic_y_overlap.to_list())


def _check_condition_overlap(
        e1: SingleExperiment,
        e2: SingleExperiment,
        ) -> list:
    
    e1_conditions = e1.omic_x.measurements.columns
    e2_conditions = e2.omic_x.measurements.columns

    condition_overlap = e1_conditions.intersection(e2_conditions)

    return condition_overlap.to_list()