"""Bind adjacent source-declared explanation/formula/supplement blocks.

No text rewriting or OCR-line heuristics. The writer must honor the returned
keep_with_next property for display equations as well as text paragraphs.
"""
from copy import deepcopy


def bind_solution_flow(blocks):
    result=deepcopy(blocks)
    for current,following in zip(result,result[1:]):
        if current.get("type")=="text" and following.get("type")=="figure" and following.get("metadata",{}).get("keep_with_previous") is True:
            current["keep_with_next"]=True
        if current.get("role")=="case_heading":
            current["keep_with_next"]=True
        if current.get("type")=="text" and (following.get("type")=="display_equation" or following.get("role")=="supplement"):
            current["keep_with_next"]=True
        if current.get("type")=="display_equation" and following.get("role")=="supplement":
            current["keep_with_next"]=True
    return result
